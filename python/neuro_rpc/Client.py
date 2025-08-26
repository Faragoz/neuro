"""
TCP client for framed JSON-RPC-like communication.

This module implements a Python client that communicates with a LabVIEW/CompactRIO
server using a custom framed JSON message protocol. It manages socket lifecycle,
message serialization, connection retries, and integration with the RPC stack.

Notes:
    - All socket operations are blocking.
    - Background operation is achieved by running the client in a thread.
"""
import socket
import struct
import threading
import time
from typing import Dict, Any, Optional

from python.neuro_rpc.Logger import Logger
from python.neuro_rpc.RPCMethods import RPCMethods
from python.neuro_rpc.Proxy import *


class ConnectionError(Exception):
    """Raised for connection-related errors (e.g., failed connect or lost connection)."""
    pass


class TimeoutError(Exception):
    """Raised when a receive operation exceeds the configured timeout."""
    pass


class MessageError(Exception):
    """Raised when a message cannot be serialized, sent, or parsed."""
    pass

import subprocess

class Client:
    """
    TCP Client for framed JSON messages.

    Manages connection lifecycle, sending/receiving messages, background thread execution,
    and integration with RPC handlers and trackers.
    """
    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 6363,
                 encoding: str = 'UTF-8',
                 endian: str = '>I',
                 timeout: float = 10.0,
                 max_retries: int = 3,
                 retry_delay: float = 1.0,
                 handler=None,
                 no_delay = True):
        """
        Initialize a Client instance with connection parameters.

        Args:
            host (str): Target hostname or IP address.
            port (int): TCP port of the server.
            encoding (str): Encoding for JSON messages.
            endian (str): Struct format for message length (e.g., ``'>I'`` big-endian).
            timeout (float): Socket timeout in seconds.
            max_retries (int): Maximum number of connection attempts.
            retry_delay (float): Delay between retry attempts in seconds.
            handler: Optional RPC handler, defaults to ``RPCMethods()``.
            no_delay (bool): If True, disables Nagle’s algorithm and sets DSCP EF.
        """
        self.host = host
        self.port = port
        self.encoding = encoding
        self.endian = endian
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.no_delay = no_delay

        self.client = None
        self.client_thread = None
        self.connected = False
        self.thread_running = False

        self.logger = Logger.get_logger(self.__class__.__name__())

        # Handling methods
        self.handler = RPCMethods()

        self.header_bytes = 4
        self.trailer_bytes = 4

    def start(self):
        """
        Start the client in a background thread.

        Notes:
            Spawns a daemon thread that calls ``connect()`` and maintains the connection.
        """
        if self.thread_running:
            self.logger.error(f"Client is already running in thread {self.client_thread.name}")
            return

        # Start the client in a separate thread
        def client_thread_func():
            try:
                self.logger.debug(f"Starting client on thread {threading.current_thread().name}")
                self.connect()
                self.thread_running = True

                # Main thread loop
                while self.thread_running:
                    # TODO: handle reconnection logic here
                    time.sleep(0.1)  # Prevent CPU hogging

            except Exception as e:
                self.logger.error(f"Client error: {e}")
            finally:
                self.logger.info("Client thread terminated")
                self.thread_running = False

        self.client_thread = threading.Thread(
            target=client_thread_func,
            name="ClientThread",
            daemon=True  # Make it a daemon so it exits when the main thread exits
        )

        self.client_thread.start()
        self.logger.debug("Client started in background thread")

    def stop(self):
        """
        Stop the client thread and disconnect.

        Calls ``disconnect()``, stops monitoring, and joins the thread.
        """
        if not self.thread_running:
            self.logger.error("Client is not running")
            return

        self.logger.info("Stopping client...")
        try:
            self.disconnect()

            # Stop monitor tracker
            self.handler.tracker.stop_monitoring()

            # Wait for thread to terminate (with timeout)
            self.client_thread.join(timeout=2.0)
            if self.client_thread.is_alive():
                self.logger.warning("Client thread did not terminate properly")

            self.thread_running = False
            self.logger.info("Client stopped")

        except Exception as e:
            self.logger.error(f"Error stopping client: {e}")

    def connect(self, retry: bool = True) -> bool:
        """
        Establish a TCP connection with retry support.

        Args:
            retry (bool): Whether to retry failed attempts.

        Returns:
            bool: True if connected successfully.

        Raises:
            ConnectionError: If all attempts fail.
        """
        attempts = 1 if not retry else self.max_retries

        for attempt in range(1, attempts + 1):
            try:
                if self.client:
                    self.disconnect()  # Close any existing connection

                self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                if self.no_delay:
                    self.client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.client.setsockopt(socket.IPPROTO_IP , socket.IP_TOS, 46 << 2)  # Set TOS for low latency
                    #self.client.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_TCLASS, 0xB8)
                    self.logger.debug("Nagle's algorithm disabled for better latency. TOS set to EF.")

                    '''try:
                        create_qos_policy_on_port(self.port)
                        self.logger.debug("QoS2 DSCP EF applied via QOSAddSocketToFlow/QOSSetFlow2")
                    except Exception as e:
                        self.logger.warning(f"QoS2 setup failed: {e}")'''

                self.client.settimeout(self.timeout)
                self.client.connect((self.host, self.port))
                self.connected = True
                self.logger.info(f"Connected to server at {self.host}:{self.port}")

                return True

            except socket.error as e:
                if attempt < attempts:
                    self.logger.warning(f"Connection attempt {attempt} failed: {e}. Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    self.logger.error(f"Failed to connect after {attempts} attempts: {e}")
                    self.client = None
                    self.connected = False
                    raise ConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}")

        return False

    def disconnect(self) -> None:
        """
        Close the TCP connection.

        Notes:
            Resets the socket and updates state to disconnected.
        """
        if self.client:
            try:
                self.client.close()
            except socket.error as e:
                self.logger.warning(f"Error during disconnection: {e}")
            finally:
                self.client = None
                self.connected = False
                self.logger.info("Disconnected from server")

    def ensure_connected(self) -> None:
        """
        Verify connection before sending/receiving.

        Raises:
            ConnectionError: If not connected.
        """
        if not self.connected or self.client is None:
            raise ConnectionError("Not connected to server. Call connect() first.")

    def _build_packet(self, data, tail = 0):
        """
        Build a framed packet with header, payload, and trailer.

        Args:
            data (dict | str | bytes): Payload data.
            tail (int): Optional trailer integer.

        Returns:
            bytes: Complete packet ready to send.

        Raises:
            TypeError: If ``data`` is not ``str`` or ``bytes`` after JSON serialization for ``dict``.
        """
        # TODO: Check endianess
        if isinstance(data, dict):
            data = json.dumps(data)

        header = (len(data) + self.trailer_bytes).to_bytes(self.header_bytes)
        trailer = tail.to_bytes(self.trailer_bytes)

        packet = bytearray()
        packet.extend(header)                       # 4 bytes header
        if isinstance(data, str):
            packet.extend(data.encode(self.encoding))   # n bytes payload
        elif isinstance(data, bytes):
            packet.extend(data)
        else:
            raise TypeError('data must be str or bytes')
        packet.extend(trailer)                      # 4 bytes tail
        return packet

    def _unbuild_packet(self, packet, size: int):
        """
        Parse a framed packet into payload and trailer.

        Args:
            packet (bytes): Raw packet.
            size (int): Declared size.

        Returns:
            tuple[bytes, int]: Payload bytes and trailer integer.
        """
        data = packet[:size-self.trailer_bytes]
        tail = int.from_bytes(packet[-self.trailer_bytes:])
        return data, tail

    def send_message(self,
                     message: Dict[str, Any],
                     retry_on_error: bool = True) -> bool:
        """
        Send a JSON message with retry support.

        Args:
            message (dict): JSON-compatible message.
            retry_on_error (bool): Whether to retry on socket errors.

        Returns:
            bool: True if sent successfully.

        Raises:
            ConnectionError: If not connected.
            MessageError: If serialization or send fails.
        """
        self.ensure_connected()

        attempts = 1 if not retry_on_error else self.max_retries

        for attempt in range(1, attempts + 1):
            try:
                # Serialize message as JSON
                message_json = json.dumps(message)

                # Send the size of the message first
                message_size = len(message_json)
                self.client.sendall(struct.pack(self.endian, message_size))

                # Send the actual message
                self.client.sendall(message_json.encode(self.encoding))

                #self.logger.debug(f"Sent: {message}")
                return True

            except (socket.error, struct.error) as e:
                if attempt < attempts:
                    self.logger.warning(f"Send attempt {attempt} failed: {e}. Retrying...")
                    # Try to reconnect before retrying
                    try:
                        self.connect(retry=False)
                    except ConnectionError:
                        pass  # Will be caught in the next iteration
                else:
                    self.logger.error(f"Failed to send message after {attempts} attempts: {e}")
                    raise MessageError(f"Failed to send message: {e}")

        return False

    def receive_message(self,
                        timeout: Optional[float] = None,
                        partial_timeout: Optional[float] = None) -> Any:
        """
        Receive and parse a JSON message.

        Args:
            timeout (float | None): Optional override for socket timeout.
            partial_timeout (float | None): Timeout for the remainder after the header.

        Returns:
            dict: Parsed JSON response.

        Raises:
            ConnectionError: If disconnected.
            TimeoutError: If operation times out.
            MessageError: If parsing fails.
        """
        self.ensure_connected()

        # Set timeout for this operation if provided
        original_timeout = None
        if timeout is not None:
            original_timeout = self.client.gettimeout()
            self.client.settimeout(timeout)

        try:
            # Read the message size
            message_size_data = self._recv_exactly(4)

            # Unpack the message size
            message_size = struct.unpack(self.endian, message_size_data)[0]

            # Set partial timeout for remainder of message if specified
            if partial_timeout is not None and original_timeout is None:
                original_timeout = self.client.gettimeout()
                self.client.settimeout(partial_timeout)

            # Read the actual message based on the size
            message_data = self._recv_exactly(message_size)

            # Decode and parse the message
            response = json.loads(message_data.decode(self.encoding))
            return response

        except socket.timeout as e:
            self.logger.error(f"Timeout receiving message: {e}")
            raise TimeoutError(f"Timed out waiting for response: {e}")

        except socket.error as e:
            self.logger.error(f"Socket error: {e}")
            self.connected = False  # Mark as disconnected since the connection probably dropped
            raise ConnectionError(f"Connection error while receiving: {e}")

        except (struct.error, json.JSONDecodeError) as e:
            self.logger.error(f"Error parsing message: {e}")
            raise MessageError(f"Invalid message format: {e}")

        finally:
            # Restore original timeout if it was changed
            if original_timeout is not None:
                self.client.settimeout(original_timeout)

    def _recv_exactly(self, n: int) -> bytes:
        """
        Receive exactly ``n`` bytes.

        Args:
            n (int): Number of bytes expected.

        Returns:
            bytes: Data read.

        Raises:
            ConnectionError: If socket closed before receiving.
        """
        data = b''
        remaining = n

        while remaining > 0:
            chunk = self.client.recv(remaining)
            # self.logger.info(f"Received chunk: {chunk}")
            if not chunk:  # Connection closed
                raise ConnectionError("Connection closed by server")
            data += chunk
            remaining -= len(chunk)

        return data

    def recv_packet(self):
        """
        Receive a framed packet.

        Returns:
            tuple[int, bytes, int] | None: ``(size, data_bytes, trailer_int)`` or ``None`` on error.
        """
        try:
            length_bytes = self._recv_exactly(self.header_bytes)
            size = int.from_bytes(length_bytes)
            full_packet = self._recv_exactly(size)
            data, tail = self._unbuild_packet(full_packet, size)
            # print(f"size: {size}, tail {tail}")
            return size, data, tail

        except Exception as e:
            self.logger.error(f"Error receiving packet: {e}")
            return None

    def send_packet(self, packet):
        """
        Send a raw packet.

        Args:
            packet (bytes): Complete framed packet.

        Returns:
            bool: True if sent successfully.
        """
        try:
            # Send packet
            self.client.sendall(packet)
            return True
        except Exception as e:
            self.logger.error(f"Error sending packet: {e}")
            return False

    def send_and_receive(self,
                         message: Dict[str, Any],
                         timeout: Optional[float] = None,
                         retry_on_error: bool = True) -> Any:
        """
        Convenience wrapper to send and immediately receive a message.

        Args:
            message (dict): Message to send.
            timeout (float | None): Optional receive timeout.
            retry_on_error (bool): Whether to retry on send errors.

        Returns:
            dict: Parsed JSON response.
        """
        self.send_message(message, retry_on_error)
        return self.receive_message(timeout)

    # Wrappers
    def rpc(self, method, params, response=True):
        """
        Perform an RPC call using Proxy encoding.

        Args:
            method (str): RPC method name.
            params (dict): Parameters.
            response (bool): Whether to wait for and return a response.

        Returns:
            tuple[int, str, int] | None: ``(size, json_str, tail)`` if ``response=True``, else ``None``.
        """
        proxy = Proxy()
        request = self.handler.create_request(method, params)
        request, hdr_tree = proxy.to_act(request)
        packet = self._build_packet(request)

        if response:
            self.send_packet(packet)
            size, data, tail = self.recv_packet()
            data = proxy.from_act(data, hdr_tree)
            tail = tail
            data = json.dumps(data, cls=NpEncoder)
            return size, data, tail
        else:
            self.send_packet(packet)
            return None

    def echo(self, message='test'):
        """
        Send an ``echo`` request and track its execution time.

        Args:
            message (str): String to send.
        """
        if isinstance(message, str):
            size, data, tail = self.rpc("echo", {'Message': message})
            data = json.loads(data)
            exec_time = tail

            self.handler.process_message(data)
            self.handler.tracker.set_exec_time(data['id'], exec_time)
        else:
            self.logger.error("echo message must be a string")

    def echo_benchmark(self):
        """
        Run a benchmark using echo requests with increasing payload sizes.

        Iterates over multiple message sizes, repeating each size multiple times,
        and records metrics through the Benchmark tracker.
        """
        import numpy
        sizes = numpy.linspace(0, 9600, 21, dtype=int)
        iter = 10

        self.handler.tracker.start_benchmark()
        for i, size in enumerate(sizes):
            size_progress = (i / len(sizes)) * 100
            # self.logger.info(f"Testing payload size {size} bytes - {size_progress:.1f}% complete")

            for j in range(iter):
                payload = "X" * size
                self.echo(payload)
        self.handler.tracker.stop_benchmark()

        self.handler.tracker.start_benchmark()
        for i, size in enumerate(sizes):

            for j in range(iter):
                payload = "X" * size
                self.echo(payload)
        self.handler.tracker.stop_benchmark()

        self.handler.tracker.start_benchmark()
        for i, size in enumerate(sizes):
            for j in range(iter):
                payload = "X" * size
                self.echo(payload)
        self.handler.tracker.stop_benchmark()

        #self.handler.tracker.export(format='json', filename='actor_benchmark_optimized')

if __name__ == "__main__":
    local = True

    if local:
        host = 'localhost'
    else:
        host = '172.16.100.9'

    server_config = {
        'host': host,
        'port': 2001,
        'no_delay': True,
    }
    print(server_config['host'])

    client = Client(host=server_config['host'], port=server_config['port'], no_delay=server_config['no_delay'])
    client.connect()

    client.echo_benchmark()
    #client.rpc("Display Text", {"Message": "Trying something :)", "exec_time": 0}, False)

    client.disconnect()
