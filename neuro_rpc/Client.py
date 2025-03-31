import socket
import struct
import threading
import json
import time
import code

from neuro_rpc.RPCMethods import RPCMethods
from neuro_rpc.__init__ import logger

class Client:
    def __init__(self, host: str = "127.0.0.1", port: int = 5555, handler=None,
                 encoding: str = 'UTF-8', endian: str = '>I', max_connections: int = 1):
        self.host = host
        self.port = port
        self.encoding = encoding
        self.endian = endian
        self.max_connections = max_connections

        # Handling methods
        if not handler:
            self.handler = RPCMethods()

        # Client status
        self.running = False
        self.client = None
        self.client_thread = None

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

    def start_client(self):
        """Starts the server and accepts multiple connections up to max_connections."""
        logger.info(f"Starting client on {self.host}:{self.port} with max {self.max_connections} connections...")

        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.client.bind((self.host, self.port))
        self.client.listen(5)  # Backlog size
        self.running = True

        logger.info(f"Client started on {self.host}:{self.port}. Waiting for connections...")

        try:
            while self.running:
                try:
                    # Socket timeout to allow interruptions
                    self.client.settimeout(1.0)
                    client_conn, client_addr = self.client.accept()

                    # Try to acquire semaphore without blocking
                    if not self.connection_semaphore.acquire(blocking=False):
                        # No slot available, reject connection
                        logger.info(f"Connection from {client_addr} rejected - maximum connections reached")
                        client_conn.close()
                        continue

                    # Connection accepted
                    with self.count_lock:
                        self.connection_count += 1

                    conn_id = id(client_conn)
                    logger.info(
                        f"Client connected: {conn_id} from {client_addr}. Active connections: {self.connection_count}")

                    # Create thread for this connection
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_conn, client_addr, conn_id),
                        daemon=True
                    )
                    client_thread.start()

                except socket.timeout:
                    # Accept() timeout, just continue
                    continue
                except socket.error as e:
                    if self.running:  # Only log if we're still running
                        logger.error(f"Error accepting connection: {e}")
                    continue

        finally:
            self.stop()

    def stop(self):
        """Stops the client and closes all connections."""
        logger.info("Stopping client...")
        self.running = False

        # Close main socket
        if self.client:
            self.client.close()

        logger.info("Client closed.")

    def handle_client(self, client_conn, client_addr, conn_id):
        """Handles communication with a client in a separate thread."""
        try:
            logger.info(f"Starting handler for client {conn_id} from {client_addr}")
            while self.running:
                message = self.read(client_conn, conn_id)
                if not message:
                    break
                # Process the JSON-RPC 2.0 message and get a response
                response = self.handler.process_message(message)
                if response:  # Only send response if there is one
                    self.write(client_conn, response, conn_id)

        except (socket.error, struct.error) as e:
            logger.error(f"Error with client {conn_id}: {e}")
        finally:
            logger.info(f"Client {conn_id} disconnected.")
            try:
                client_conn.close()
            except:
                pass

            # Update counter and release semaphore
            with self.count_lock:
                self.connection_count -= 1

            self.connection_semaphore.release()
            logger.info(f"Connection slot freed. Active connections: {self.connection_count}")

    def read(self, client_conn, conn_id):
        """Reads a message from a client connection."""
        try:
            message_size_data = client_conn.recv(4)
            if len(message_size_data) < 4:
                return None

            message_size = struct.unpack(self.endian, message_size_data)[0]
            message_data = client_conn.recv(message_size)
            if len(message_data) < message_size:
                return None

            logger.debug(f"[{conn_id}] << {message_data.decode(self.encoding)}")
            return json.loads(message_data.decode(self.encoding))
        except (socket.error, struct.error):
            return None

    def write(self, client_conn, response, conn_id):
        """Sends a response to a client connection."""
        try:
            message = json.dumps(response)
            message_size = len(message)
            client_conn.sendall(struct.pack(self.endian, message_size))  # Size header
            client_conn.sendall(message.encode(self.encoding))  # JSON content
            logger.debug(f"[{conn_id}] >> {message}")
        except (socket.error, struct.error):
            pass

    # Interactive consol
    def start_interactive_console(self):
        """
        Start an interactive console with access to the client object.
        The console runs in the main thread while the client runs in a background thread.

        Press Ctrl+D (or Ctrl+Z on Windows) to exit the console.
        """
        # Start client in a separate thread if it's not already running
        if not hasattr(self, 'thread') or self.client_thread is None or not self.client_thread.is_alive():
            self.client_thread = threading.Thread(target=self.start_client, daemon=True)
            self.client_thread.start()

        console_banner = (
            "\nInteractive console started.\n"
            "You can access the 'client' object directly here.\n"
            "Press Ctrl+D (or Ctrl+Z on Windows) to exit the console."
        )

        # Make client available in the console's local namespace
        local_vars = {'client': self}

        # Start the interactive console
        code.interact(banner=console_banner, local=local_vars)


if __name__ == "__main__":
    client = Client()
    server_thread = threading.Thread(target=client.start_client, daemon=True)
    server_thread.start()

    # Keep main thread alive
    try:
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        client.stop()
