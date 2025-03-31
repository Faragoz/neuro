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


class CustomLogger(logging.Logger):
    """
    Custom Logger with ANSI-colored logging and support for flexible handlers.
    """

    def __init__(self, name: str, level=logging.INFO, verbose: bool = False):
        super().__init__(name, level)

        # Set up attributes
        self.verbose = verbose

        # Add a StreamHandler
        self.stream_handler = logging.StreamHandler()
        self.addHandler(self.stream_handler)

        # Set initial levels and formatter
        self.setLevel(level)
        self._set_formatter()

    def _set_formatter(self) -> None:
        """
        Configure the formatter for the stream handler.
        """
        info = '[%(levelname)s] [%(module)s:%(lineno)d] - %(message)s'
        if self.verbose:
            info = '[%(levelname)s] [%(processName)s:%(process)d] [%(threadName)s] [%(module)s:%(lineno)d] - %(message)s'
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

if __name__ == "__main__":
    # Initialize a CustomLogger instance
    logger = CustomLogger(name="__neuro__")

    # Set logger level and verbosity
    logger.setLevel(logging.DEBUG)  # Logger and handler only process INFO level and above
    logger.setVerbose(True)  # Enable verbose logging

    logger.test()