# Library default imports
__all__ = ['logger']

# TODO: Generate documentations for GitHub Pages with mkdocs (read the docs)
#  url: https://realpython.com/python-project-documentation-with-mkdocs/
import logging

from neuro_rpc.Logger import CustomLogger

# Initialize a CustomLogger instance
logger = CustomLogger("__neuro__", logging.DEBUG, True)

if __name__ == "__main__":
    logger.test()