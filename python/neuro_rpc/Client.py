import socket
import struct
import threading
import time
from typing import Dict, Any, Optional

from python.neuro_rpc.Logger import Logger
from python.neuro_rpc.RPCMethods import RPCMethods
from python.neuro_rpc.Proxy import *


class ConnectionError(Exception):
    """Exception raised for connection-related errors."""
    pass


class TimeoutError(Exception):
    """Exception raised when an operation times out."""
    pass


class MessageError(Exception):
    """Exception raised for message-related errors."""
    pass

import subprocess


def create_qos_policy_on_port(port: int, dscp_value: int = 46):
    name = f"PyQoS_Port_{port}"
    # Construimos el comando con GUIONES ASCII (U+002D) y cmdlets correctos
    ps_cmd = (
        "Import-Module NetQos; "
        f"if (-not (Get-NetQosPolicy -Name '{name}' -ErrorAction SilentlyContinue)) {{ "
        f"    New-NetQosPolicy -Name '{name}' "
        f"-IPProtocolMatchCondition TCP -DestinationPort {port} -DSCPAction {dscp_value} "
        "}} else {{ Write-Host 'Policy already exists.' }}"
    )

    full_cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-Command", ps_cmd
    ]
    # Esto debe correrse con permisos de Administrador
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Error creando política QoS (exit {result.returncode}):\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result.stdout.strip()

class Client:
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
        Initialize a Client instance.

        Args:
            host: Client hostname or IP address
            port: Client port number
            encoding: Character encoding for messages
            endian: Byte order for message size ('>I' for big-endian, '<I' for little-endian)
            timeout: Socket timeout in seconds
            max_retries: Maximum number of connection retry attempts
            retry_delay: Delay between retry attempts in seconds
            no_delay: Disable Nagle's algorithm for better latency
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

        self.logger = Logger.get_logger(self.__class__.__name__)

        # Handling methods
        self.handler = RPCMethods()

        self.header_bytes = 4
        self.trailer_bytes = 4

    def start(self):
        """Start the client in a background thread."""
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
        """Stop the running thread client."""
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
        Establishes a connection with the server with retry mechanism.

        Args:
            retry: Whether to retry failed connection attempts

        Returns:
            True if connection successful, False otherwise

        Raises:
            ConnectionError: If connection fails after all retries
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
        Closes the connection with the server.
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
        Ensures that the server is connected before attempting communication.

        Raises:
            ConnectionError: If the server is not connected
        """
        if not self.connected or self.client is None:
            raise ConnectionError("Not connected to server. Call connect() first.")

    def _build_packet(self, data, tail = 0):
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
        data = packet[:size-self.trailer_bytes]
        tail = int.from_bytes(packet[-self.trailer_bytes:])
        return data, tail

    def send_message(self,
                     message: Dict[str, Any],
                     retry_on_error: bool = True) -> bool:
        """
        Sends a JSON message to the server with retry mechanism.

        Args:
            message: Dictionary to be sent as JSON
            retry_on_error: Whether to retry on connection errors

        Returns:
            True if message sent successfully, False otherwise

        Raises:
            ConnectionError: If server is not connected or connection fails
            MessageError: If there's an error encoding or sending the message
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
        Receives and parses a JSON response from the server.

        Args:
            timeout: Optional timeout override for this specific receive operation
            partial_timeout: Timeout for receiving the remainder of a partial message

        Returns:
            Parsed JSON response

        Raises:
            ConnectionError: If server is not connected
            TimeoutError: If receive operation times out
            MessageError: If message cannot be parsed
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
        Receives exactly n bytes from the socket, blocking until all bytes are received.

        Args:
            n: Number of bytes to receive

        Returns:
            Exactly n bytes of metadata

        Raises:
            socket.error: If a socket error occurs
            ConnectionError: If connection is closed before receiving all bytes
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
        Send a data packet with reliable byte writing.
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
        Convenience method to send a message and wait for a response.

        Args:
            message: Dictionary to be sent as JSON
            timeout: Timeout for receiving the response
            retry_on_error: Whether to retry on connection errors

        Returns:
            Parsed JSON response

        Raises:
            ConnectionError: If server is not connected
            TimeoutError: If receive operation times out
            MessageError: If message cannot be parsed or sent
        """
        self.send_message(message, retry_on_error)
        return self.receive_message(timeout)

    # Wrappers
    def rpc(self, method, params, response=True):
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
        if isinstance(message, str):
            size, data, tail = self.rpc("echo", {'Message': message})
            data = json.loads(data)
            exec_time = tail

            self.handler.process_message(data)
            self.handler.tracker.set_exec_time(data['id'], exec_time)
        else:
            self.logger.error("echo message must be a string")

    def echo_benchmark(self):
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