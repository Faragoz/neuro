# Library default imports
__all__ = ['logger']

# TODO: Generate documentations for GitHub Pages with mkdocs (read the docs)
#  url: https://realpython.com/python-project-documentation-with-mkdocs/

from python.neuro_rpc.Logger import Logger

# Initialize a Logger instance
logger = Logger.get_logger("__neuro__")

if __name__ == "__main__":
    pass