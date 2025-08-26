"""
@file Logger.py
@brief Colorized, structured logging utilities for the NeuroRPC stack.
@details Provides a compact ANSI color formatter and a reusable Logger factory.
All modules (Client, Benchmark, RPC stack, Console) use this centralized logging
infrastructure to ensure consistent formatting and runtime readability.
@note Uses colorama for cross-platform color handling. Verbosity can be adjusted dynamically.
"""

import logging

from colorama import Fore, Back, Style, init

# Initialize colorama for cross-platform compatibility
init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """
    @brief Minimal ANSI color formatter.
    @details Extends logging.Formatter to prepend log messages with ANSI color codes
    depending on the log level. Colors are reset automatically after each message.
    """
    COLORS = {
        logging.DEBUG: Fore.BLUE,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Back.RED + Fore.WHITE,
    }
    RESET = Style.RESET_ALL

    def format(self, record):
        """
        @brief Apply color formatting to a log record.
        @param record logging.LogRecord Log record object to format.
        @return str Formatted string with ANSI colors.
        @note Original message content is preserved; only colored prefix/suffix is added.
        """
        msg = super().format(record)
        color = self.COLORS.get(record.levelno, self.RESET)
        return f"{color}{msg}{self.RESET}"


class Logger(logging.Logger):
    """
    @class Logger
    @brief Factory for module-level loggers with a shared format.
    @details Ensures all modules share a consistent format and color scheme.
    Provides caching of Logger instances by name, synchronized levels, and verbosity toggling.
    """
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    # Dictionary to store loggers by name
    _instances = {}

    @staticmethod
    def print_loggers():
        """
        @brief Print currently registered loggers.
        @details Useful for debugging which loggers are active and their configuration.
        """
        #= lambda: print(Logger._instances)
        for name, logger in Logger._instances.items():
            print(f"{name}: {logger} {logger.handlers} {logger.level}")

    @staticmethod
    def get_logger(name="__neuro__", level=logging.DEBUG, verbose=True):
        """
        @brief Get or create a configured logger.
        @param name str Logger identifier (typically module or class name).
        @param level int Log level (default DEBUG).
        @param verbose bool Whether to include extended context (process/thread info).
        @return Logger Configured logger instance.
        @note Attaches a StreamHandler on first creation.
        """
        if name not in Logger._instances:
            Logger._instances[name] = Logger(name, level, verbose)
        return Logger._instances[name]

    def __init__(self, name: str, level=logging.DEBUG, verbose: bool = True):
        """
        @brief Initialize a Logger instance.
        @param name str Name of the logger.
        @param level int Log level.
        @param verbose bool Whether verbose format is enabled.
        """
        super().__init__(name, level)

        # Set up attributes
        self.verbose = verbose

        # Add a StreamHandler
        import sys
        self.stream_handler = logging.StreamHandler(sys.stdout)
        self.addHandler(self.stream_handler)

        # Set initial levels and formatter
        self.setLevel(level)
        self._set_formatter()

        #self.debug(f"Logger '{name}' initialized.")

    def _set_formatter(self) -> None:
        """
        @brief Configure formatter for the stream handler.
        @details Chooses between compact and verbose formats depending on verbosity flag.
        """
        info = '[%(levelname)s] [%(name)s] [%(module)s:%(lineno)d] - %(message)s'
        if self.verbose:
            info = '[%(levelname)s] [%(name)s] [%(processName)s:%(process)d] [%(threadName)s] [%(module)s:%(lineno)d] - %(message)s'
        formatter = ColoredFormatter(info)
        self.stream_handler.setFormatter(formatter)

    def setLevel(self, level) -> None:
        """
        @brief Override setLevel to synchronize handler level.
        @param level int New log level.
        """
        super().setLevel(level)
        self.stream_handler.setLevel(level)  # Ensure handler level matches logger level

    def setVerbose(self, verbose: bool) -> None:
        """
        @brief Dynamically update verbosity and re-apply formatter.
        @param verbose bool True for detailed context, False for compact output.
        """
        self.verbose = verbose
        self._set_formatter()

    def test(self) -> None:
        """
        @brief Emit test messages at all levels.
        @details Useful for verifying logger color and format configuration.
        """
        # Log messages of different levels
        self.debug("This is a DEBUG message.")
        self.info("This is an INFO message.")
        self.warning("This is a WARNING message.")
        self.error("This is an ERROR message.")
        self.critical("This is a CRITICAL message.")

class LoggerConfig:
    """
    @class LoggerConfig
    @brief Default logging configuration holder.
    @details Provides presets for production, development, and per-component debugging.
    """

    @staticmethod
    def configure_for_production():
        """
        @brief Configure all loggers for production.
        @details Sets INFO level and disables verbose formatting.
        """
        # Configurar loggers por defecto
        for name, logger_instance in Logger._instances.items():
            logger_instance.setLevel(logging.INFO)
            logger_instance.setVerbose(False)


    @staticmethod
    def configure_for_development():
        """
        @brief Configure all loggers for development.
        @details Sets DEBUG level and enables verbose formatting.
        """
        for name, logger_instance in Logger._instances.items():
            logger_instance.setLevel(logging.DEBUG)
            logger_instance.setVerbose(True)

    @staticmethod
    def configure_for_debugging(component_name, level=logging.DEBUG, verbose=True):
        """
        @brief Configure a specific component for debugging.
        @param component_name str Name of the component/logger.
        @param level int Log level (default DEBUG).
        @param verbose bool Verbosity flag.
        @note Creates a new logger if not already registered.
        """
        if component_name in Logger._instances:
            Logger._instances[component_name].setLevel(level)
            Logger._instances[component_name].setVerbose(verbose)
        else:
            Logger.get_logger(component_name, level, verbose)
            Logger._instances[component_name].warning(f"Logger '{component_name}' not found. Creating a new one.")

if __name__ == "__main__":
    # Initialize a Logger instance
    logger = Logger.get_logger("__neuro__")
    test_logger = Logger.get_logger("__test__")

    print("Loggers: ")
    Logger.print_loggers()

    print("DEVELOPMENT: ")
    LoggerConfig.configure_for_development()
    Logger.print_loggers()
    logger.test()
    test_logger.test()

    print("PRODUCTION: ")
    LoggerConfig.configure_for_production()
    Logger.print_loggers()
    logger.test()
    test_logger.test()

    print("DEBUGGING: ")
    LoggerConfig.configure_for_debugging("__test__", level = Logger.WARNING, verbose = False)
    Logger.print_loggers()
    test_logger.test()