import code
import threading
import time
import os
import platform

from neuro_rpc.Logger import Logger, LoggerConfig
from neuro_rpc.Client import Client

class Console:
    """
    A simple interactive console that allows user to manually start
    an RPC client when needed.
    """

    def __init__(self, client_config=None):
        """
        Initialize the interactive console with client configuration.

        Args:
            client_config: Dictionary with client configuration parameters
        """
        self.client_class = Client
        self.client_config = client_config or {}
        self.client = None
        self.running = False
        self.logger = Logger.get_logger(self.__class__.__name__)

    def start_client(self):
        """Start the client in a background thread."""
        # Use existing client instance or create a new one if needed
        if self.client is None:
            self.client = self.client_class(**self.client_config)

        self.client.start()

    def stop_client(self):
        """Stop the thread_running client."""
        if self.client is None:
            self.logger.error("Client object not initialized")
            return

        self.client.stop()

    def client_status(self):
        """Check and display the current status of the client."""
        status = ["\n"]

        # Check if client object exists
        if self.client is None:
            status.append("Client not initialized")
            status.append("To initialize and connect the client, use: start()")
            self.logger.error("\n".join(status))
            return

        # If client exists, check its status
        status.append(f"Client object: {type(self.client).__name__}")
        status.append(f"Client connected: {self.client.connected}")

        if self.running:
            status.append(f"Client thread_running in thread: {self.client.client_thread.name}")
            status.append(f"Thread alive: {self.client.client_thread.is_alive()}")
        else:
            status.append("Client not thread_running in background")

        # TODO: Not printing methods. Check client instance.
        # If client has a handler, show method information
        if hasattr(self.client, 'handler'):
            handler = self.client.handler
            if hasattr(handler, 'request_methods'):
                status.append(f"Request methods: {list(handler.request_methods.keys())}")
            if hasattr(handler, 'response_methods'):
                status.append(f"Response methods: {list(handler.response_methods.keys())}")

        self.logger.info("\n".join(status))

    def clear_screen(self) -> None:
        """Clear the console screen based on the operating system."""
        system = platform.system().lower()

        if system == 'windows':
            os.system('cls')
        else:  # For Linux, macOS, etc.
            os.system('clear')

    def run(self):
        """Run the interactive console first, with lazy client initialization."""
        try:
            # Initialize client object but don't connect yet
            # self.initialize_client()

            # Start the interactive console immediately
            self.start_interactive_console()

        except KeyboardInterrupt:
            self.logger.error("\nInterrupted by user")
        finally:
            # Make sure to clean up
            if self.running:
                self.stop_client()
            self.logger.info("Goodbye!")

    def start_interactive_console(self):
        """Start the simple interactive console."""
        # Prepare the welcome message
        banner = """
=================================================================
RPC Client Interactive Console
=================================================================

The client is not thread_running yet. To start it, use:
    start()

Client object is available as 'client' variable.
Once started, use client().method() to interact with the client.

Available commands:
    start() - Start the client in background
    stop()  - Stop the thread_running client
    status() - Get the status of the client
    cls() - Clear the console screen

Available modules:
    logger - NeuroRPC logger
    config_logger - NeuroRPC logger configuration

Press Ctrl+D (or Ctrl+Z on Windows) to exit the console.
=================================================================
"""

        # Prepare the namespace for the console
        namespace = {
            'client': lambda: self.client,
            'start': self.start_client,
            'stop': self.stop_client,
            'status': self.client_status,
            'cls': self.clear_screen,
            'logger': Logger,
            'config_logger': LoggerConfig,
        }

        # Create and start the console
        console = code.InteractiveConsole(locals=namespace)
        console.interact(banner=banner)

        # When console exits, make sure to clean up
        self.logger.info("Exiting interactive console...")
        if self.running:
            self.stop_client()


# Example usage:
if __name__ == "__main__":
    # Configuration for the client
    client_config = {
        'host': 'localhost',
        'port': 6340
    }

    # Create and run the interactive console
    console = Console(client_config)
    console.run()
