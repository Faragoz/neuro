import socket
import struct
import threading
import json
import code

from neuro_rpc.RPCMethods import RPCMethods
from neuro_rpc.Logger import Logger

class Client:
    def __init__(self, host: str = "127.0.0.1", port: int = 5555, handler=None,
                 encoding: str = 'UTF-8', endian: str = '>I', max_connections: int = 1):
        self.host = host
        self.port = port
        self.encoding = encoding
        self.endian = endian
        self.max_connections = max_connections

        self.logger = Logger.get_logger(self.__class__.__name__, Logger.WARNING
                                        )

        # Handling methods
        if not handler:
            self.handler = RPCMethods()

        # Client status
        self.running = False
        self.server = None
        self.server_thread = None

        # Semaphore to limit concurrent connections
        self.connection_semaphore = threading.Semaphore(max_connections)
        self.connection_count = 0
        self.count_lock = threading.Lock()

        # Auto-start
        self.handler.tracker.start_monitoring()
        self.start_interactive_console()

    def __str__(self):
        if self.running:
            return f"Running on {self.host}:{self.port} with {self.connection_count}/{self.max_connections} connections"
        else:
            return f"Disconnected"

    def start(self):
        """Starts the server and accepts multiple connections up to max_connections."""
        self.logger.info(f"Starting server on {self.host}:{self.port} with max {self.max_connections} connections...")

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(5)  # Backlog size
        self.running = True

        self.logger.info(f"Client started on {self.host}:{self.port}. Waiting for connections...")

        try:
            while self.running:
                try:
                    # Socket timeout to allow interruptions
                    self.server.settimeout(1.0)
                    server_conn, server_addr = self.server.accept()

                    # Try to acquire semaphore without blocking
                    if not self.connection_semaphore.acquire(blocking=False):
                        # No slot available, reject connection
                        self.logger.info(f"Connection from {server_addr} rejected - maximum connections reached")
                        server_conn.close()
                        continue

                    # Connection accepted
                    with self.count_lock:
                        self.connection_count += 1

                    conn_id = id(server_conn)
                    self.logger.info(
                        f"Client connected: {conn_id} from {server_addr}. Active connections: {self.connection_count}")

                    # Create thread for this connection
                    server_thread = threading.Thread(
                        target=self.handle_server,
                        args=(server_conn, server_addr, conn_id),
                        daemon=True
                    )
                    server_thread.start()

                except socket.timeout:
                    # Accept() timeout, just continue
                    continue
                except socket.error as e:
                    if self.running:  # Only log if we're still thread_running
                        self.logger.error(f"Error accepting connection: {e}")
                    continue

        finally:
            self.stop()

    def stop(self):
        """Stops the server and closes all connections."""
        self.logger.info("Stopping server...")
        self.running = False

        # Close main socket
        if self.server:
            self.server.close()

        self.logger.info("Client closed.")

    def handle_server(self, server_conn, server_addr, conn_id):
        """Handles communication with a server in a separate thread."""
        try:
            self.logger.info(f"Starting handler for server {conn_id} from {server_addr}")
            while self.running:
                message = self.read(server_conn, conn_id)
                if not message:
                    break
                # Process the JSON-RPC 2.0 message and get a response
                response = self.handler.process_message(message)
                if response:  # Only send response if there is one
                    self.write(server_conn, response, conn_id)

        except (socket.error, struct.error) as e:
            self.logger.error(f"Error with server {conn_id}: {e}")
        finally:
            self.logger.info(f"Client {conn_id} disconnected.")
            try:
                server_conn.close()
            except:
                pass

            # Update counter and release semaphore
            with self.count_lock:
                self.connection_count -= 1

            self.connection_semaphore.release()
            self.logger.info(f"Connection slot freed. Active connections: {self.connection_count}")

    def read(self, server_conn, conn_id):
        """Reads a message from a server connection."""
        try:
            message_size_data = server_conn.recv(4)
            if len(message_size_data) < 4:
                return None

            message_size = struct.unpack(self.endian, message_size_data)[0]
            message_data = server_conn.recv(message_size)
            if len(message_data) < message_size:
                return None

            self.logger.debug(f"[{conn_id}] << {message_data.decode(self.encoding)}")
            return json.loads(message_data.decode(self.encoding))
        except (socket.error, struct.error):
            return None

    def write(self, server_conn, response, conn_id):
        """Sends a response to a server connection."""
        try:
            message = json.dumps(response)
            message_size = len(message)
            server_conn.sendall(struct.pack(self.endian, message_size))  # Size header
            server_conn.sendall(message.encode(self.encoding))  # JSON content
            self.logger.debug(f"[{conn_id}] >> {message}")
        except (socket.error, struct.error):
            pass

    # Interactive consol
    def start_interactive_console(self):
        """
        Start an interactive console with access to the server object.
        The console runs in the main thread while the server runs in a background thread.

        Press Ctrl+D (or Ctrl+Z on Windows) to exit the console.
        """
        # Start server in a separate thread if it's not already thread_running
        if not hasattr(self, 'thread') or self.server_thread is None or not self.server_thread.is_alive():
            self.server_thread = threading.Thread(target=self.start, name="RPC-Interactive-Console", daemon=True)
            self.server_thread.start()

        console_banner = (
            "\nInteractive console started.\n"
            "You can access the 'server' object directly here.\n"
            "Press Ctrl+D (or Ctrl+Z on Windows) to exit the console."
        )

        # Make server available in the console's local namespace
        local_vars = {'server': self}

        # Start the interactive console
        code.interact(banner=console_banner, local=local_vars)


if __name__ == "__main__":
    server = Server()
    server_thread = threading.Thread(target=server.start, daemon=True)
    server_thread.start()

    # Keep main thread alive
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        server.stop()
