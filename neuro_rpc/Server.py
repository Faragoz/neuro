import socket
import struct
import json
import time
from typing import Any, Dict, Optional, Union, Tuple, Callable
from neuro_rpc import logger


class ConnectionError(Exception):
    """Exception raised for connection-related errors."""
    pass


class TimeoutError(Exception):
    """Exception raised when an operation times out."""
    pass


class MessageError(Exception):
    """Exception raised for message-related errors."""
    pass


class Server:
    def __init__(self,
                 host: str = "127.0.0.1",
                 port: int = 5555,
                 encoding: str = 'UTF-8',
                 endian: str = '>I',
                 timeout: float = 30.0,
                 max_retries: int = 3,
                 retry_delay: float = 1.0):
        """
        Initialize a Server instance.

        Args:
            host: Server hostname or IP address
            port: Server port number
            encoding: Character encoding for messages
            endian: Byte order for message size ('>I' for big-endian, '<I' for little-endian)
            timeout: Socket timeout in seconds
            max_retries: Maximum number of connection retry attempts
            retry_delay: Delay between retry attempts in seconds
        """
        self.host = host
        self.port = port
        self.encoding = encoding
        self.endian = endian
        self.server = None
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connected = False

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
                if self.server:
                    self.disconnect()  # Close any existing connection

                self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.server.settimeout(self.timeout)
                self.server.connect((self.host, self.port))
                self.connected = True
                logger.info(f"Connected to server at {self.host}:{self.port}")
                return True

            except socket.error as e:
                if attempt < attempts:
                    logger.warning(f"Connection attempt {attempt} failed: {e}. Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Failed to connect after {attempts} attempts: {e}")
                    self.server = None
                    self.connected = False
                    raise ConnectionError(f"Failed to connect to {self.host}:{self.port}: {e}")

        return False

    def disconnect(self) -> None:
        """
        Closes the connection with the server.
        """
        if self.server:
            try:
                self.server.close()
            except socket.error as e:
                logger.warning(f"Error during disconnection: {e}")
            finally:
                self.server = None
                self.connected = False
                logger.info("Disconnected from server")

    def ensure_connected(self) -> None:
        """
        Ensures that the server is connected before attempting communication.

        Raises:
            ConnectionError: If the server is not connected
        """
        if not self.connected or self.server is None:
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
                message_json = json.dumps(message).encode(self.encoding)

                # Send the size of the message first
                message_size = len(message_json)
                self.server.sendall(struct.pack(self.endian, message_size))

                # Send the actual message
                self.server.sendall(message_json)

                logger.debug(f"Sent: {message}")
                return True

            except (socket.error, struct.error) as e:
                if attempt < attempts:
                    logger.warning(f"Send attempt {attempt} failed: {e}. Retrying...")
                    # Try to reconnect before retrying
                    try:
                        self.connect(retry=False)
                    except ConnectionError:
                        pass  # Will be caught in the next iteration
                else:
                    logger.error(f"Failed to send message after {attempts} attempts: {e}")
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
            original_timeout = self.server.gettimeout()
            self.server.settimeout(timeout)

        try:
            # Read the message size
            message_size_data = self._recv_exactly(4)

            # Unpack the message size
            message_size = struct.unpack(self.endian, message_size_data)[0]

            # Set partial timeout for remainder of message if specified
            if partial_timeout is not None and original_timeout is None:
                original_timeout = self.server.gettimeout()
                self.server.settimeout(partial_timeout)

            # Read the actual message based on the size
            message_data = self._recv_exactly(message_size)

            # Decode and parse the message
            response = json.loads(message_data.decode(self.encoding))
            logger.debug(f"Received: {response}")
            return response

        except socket.timeout as e:
            logger.error(f"Timeout receiving message: {e}")
            raise TimeoutError(f"Timed out waiting for response: {e}")

        except socket.error as e:
            logger.error(f"Socket error: {e}")
            self.connected = False  # Mark as disconnected since the connection probably dropped
            raise ConnectionError(f"Connection error while receiving: {e}")

        except (struct.error, json.JSONDecodeError) as e:
            logger.error(f"Error parsing message: {e}")
            raise MessageError(f"Invalid message format: {e}")

        finally:
            # Restore original timeout if it was changed
            if original_timeout is not None:
                self.server.settimeout(original_timeout)

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
            chunk = self.server.recv(remaining)
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


if __name__ == "__main__":
    # Example server usage
    server = Server(max_retries=2, timeout=10.0)

    try:
        # Connect with retry mechanism
        server.connect()

        # Example message to send to the server
        message = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "echo",
            "params": {"message": "Hello, Server!"}
        }

        # Send message and wait for response
        try:
            response = server.send_and_receive(message)
            logger.info(f"Response received: {response}")
        except (ConnectionError, TimeoutError, MessageError) as e:
            logger.error(f"Communication error: {e}")

        # Another example with different message
        add_message = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "add",
            "params": {"a": 5, "b": 8}
        }

        try:
            add_response = server.send_and_receive(add_message)
            logger.info(f"Add result: {add_response}")
        except (ConnectionError, TimeoutError, MessageError) as e:
            logger.error(f"Communication error: {e}")

    except ConnectionError as e:
        logger.error(f"Failed to connect: {e}")
    finally:
        server.disconnect()
