"""
@file Console.py
@brief Interactive console wrapper for NeuroRPC client.
@details Provides a REPL-style interface to manually start, stop, and inspect the state of
the TCP client. The console is useful for debugging and testing RPC connections interactively.
@note Runs with Python's built-in InteractiveConsole. Available commands and modules are preloaded
in the interactive namespace.
"""

import code
import os
import platform

from python.neuro_rpc.Logger import Logger, LoggerConfig
from python.neuro_rpc.Client import Client

class Console:
    """
    @brief Interactive console for manual client control.
    @details Encapsulates startup and shutdown logic for the NeuroRPC client and
    exposes convenience commands in an interactive REPL environment.
    Provides status checks and log outputs for debugging.
    """

    def __init__(self, client_config=None):
        """
        @brief Initialize the interactive console with client configuration.
        @param client_config dict Optional dictionary of client configuration parameters (host, port, etc.).
        @note If no config is provided, defaults are used by Client.
        """
        self.client_class = Client
        self.client_config = client_config or {}
        self.client = None
        self.running = False
        self.logger = Logger.get_logger(self.__class__.__name__)

    def start_client(self):
        """
        @brief Start the client in a background thread.
        @details Instantiates Client if not yet created and calls start().
        """
        # Use existing client instance or create a new one if needed
        if self.client is None:
            self.client = self.client_class(**self.client_config)

        self.client.start()

    def stop_client(self):
        """
        @brief Stop the running client thread.
        @details Calls Client.stop(). Logs error if client is uninitialized.
        """
        if self.client is None:
            self.logger.error("Client object not initialized")
            return

        self.client.stop()

    def client_status(self):
        """
        @brief Display current client status in the logger.
        @details Prints information about the client object, connection status,
        active thread, and registered RPC methods (if handler available).
        """
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
        """
        @brief Clear the console screen.
        @details Uses OS-specific commands: 'cls' on Windows, 'clear' on Unix-like systems.
        """
        system = platform.system().lower()

        if system == 'windows':
            os.system('cls')
        else:  # For Linux, macOS, etc.
            os.system('clear')

    def run(self):
        """
        @brief Run the interactive console.
        @details Initializes the interactive console and blocks until exit.
        Handles Ctrl+C gracefully, stopping the client if necessary.
        """
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
        """
        @brief Start the REPL console with preloaded commands.
        @details Provides start/stop/status/cls commands and access to Logger and LoggerConfig.
        A banner with usage instructions is displayed at startup.
        """
        # Prepare the welcome message
        banner = """
=================================================================
Message Client Interactive Console
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
