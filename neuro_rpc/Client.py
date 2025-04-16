import socket
import struct
import json
import threading
import time
from random import randint
from typing import Any, Dict, Optional, Union, Tuple, Callable
from neuro_rpc.Logger import Logger
from neuro_rpc.RPCMethods import RPCMethods


class ConnectionError(Exception):
    """Exception raised for connection-related errors."""
    pass


class TimeoutError(Exception):
    """Exception raised when an operation times out."""
    pass


class MessageError(Exception):
    """Exception raised for message-related errors."""
    pass


class Client:
    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 6340,
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
                    self.logger.debug("Nagle's algorithm disabled for better latency.")

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
            Exactly n bytes of data

        Raises:
            socket.error: If a socket error occurs
            ConnectionError: If connection is closed before receiving all bytes
        """
        data = b''
        remaining = n

        while remaining > 0:
            chunk = self.client.recv(remaining)
            if not chunk:  # Connection closed
                raise ConnectionError("Connection closed by server")
            data += chunk
            remaining -= len(chunk)

        return data

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
        message = self.handler.create_request(method,params)

        if response:
            return self.send_and_receive(message)
        else:
            self.send_message(message)
            return None

    def echo(self, message='test'):
        if isinstance(message, str):
            self.handler.process_message(self.rpc("echo", {'message': message}))
        else:
            self.logger.error("echo message must be a string")

    def echo_benchmark(self):
        self.handler.tracker.start_benchmark()

        for i in range(100):
            payload = "X" * randint(0, 3000)
            self.echo(payload)

        print(json.dumps(self.handler.tracker.stop_benchmark(), indent=4))

if __name__ == "__main__":
    client = Client(host='172.16.100.9', port=6340, max_retries=2, timeout=10.0)
    client.start()
#server = Client(host='172.16.100.9', port=6340, max_retries=2, timeout=10.0)
