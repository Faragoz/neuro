import logging

from colorama import Fore, Back, Style, init

# Initialize colorama for cross-platform compatibility
init(autoreset=True)

class ColoredFormatter(logging.Formatter):
    """
    Custom Formatter that applies colors to log levels using ANSI codes.
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
        Overrides the default format method to add color to log levels.
        """
        msg = super().format(record)
        color = self.COLORS.get(record.levelno, self.RESET)
        return f"{color}{msg}{self.RESET}"


class Logger(logging.Logger):
    """
    Custom Logger with ANSI-colored logging and support for flexible handlers.
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
        #= lambda: print(Logger._instances)
        for name, logger in Logger._instances.items():
            print(f"{name}: {logger} {logger.handlers} {logger.level}")

    @staticmethod
    def get_logger(name="__neuro__", level=logging.DEBUG, verbose=True):
        """
        Get or create a logger instance with the given name.

        Args:
            name (str): Logger name
            level (int): Logging level
            verbose (bool): Whether to use verbose format

        Returns:
            Logger: The logger instance for the given name
        """
        if name not in Logger._instances:
            Logger._instances[name] = Logger(name, level, verbose)
        return Logger._instances[name]

    def __init__(self, name: str, level=logging.DEBUG, verbose: bool = True):
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
        Configure the formatter for the stream handler.
        """
        info = '[%(levelname)s] [%(name)s] [%(module)s:%(lineno)d] - %(message)s'
        if self.verbose:
            info = '[%(levelname)s] [%(name)s] [%(processName)s:%(process)d] [%(threadName)s] [%(module)s:%(lineno)d] - %(message)s'
        formatter = ColoredFormatter(info)
        self.stream_handler.setFormatter(formatter)

    def setLevel(self, level) -> None:
        """
        Override logger level setter to synchronize both logger and stream handler levels.
        """
        super().setLevel(level)
        self.stream_handler.setLevel(level)  # Ensure handler level matches logger level

    def setVerbose(self, verbose: bool) -> None:
        """
        Dynamically updates the verbosity and re-applies the formatter.
        """
        self.verbose = verbose
        self._set_formatter()

    def test(self) -> None:
        # Log messages of different levels
        self.debug("This is a DEBUG message.")
        self.info("This is an INFO message.")
        self.warning("This is a WARNING message.")
        self.error("This is an ERROR message.")
        self.critical("This is a CRITICAL message.")

class LoggerConfig:
    @staticmethod
    def configure_for_production():
        """Configure all loggers for production environment"""
        # Configurar loggers por defecto
        for name, logger_instance in Logger._instances.items():
            logger_instance.setLevel(logging.INFO)
            logger_instance.setVerbose(False)


    @staticmethod
    def configure_for_development():
        """Configure all loggers for development environment"""
        for name, logger_instance in Logger._instances.items():
            logger_instance.setLevel(logging.DEBUG)
            logger_instance.setVerbose(True)

    @staticmethod
    def configure_for_debugging(component_name, level=logging.DEBUG, verbose=True):
        """Configure a specific component for detailed debugging"""
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