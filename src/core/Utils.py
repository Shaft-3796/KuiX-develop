"""
This module contains utility classes, functions and stuff for KuiX
"""
import threading
from dataclasses import dataclass
import traceback as tba

# EOF character for socket communication
EOT = "04"


# Terminal colors
@dataclass
class C:
    """
    Pre defined terminal colors codes
    """
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    GRAY = '\033[37m'

    BBLACK = '\033[40m'
    BRED = '\033[41m'
    BGREEN = '\033[42m'
    BYELLOW = '\033[43m'
    BBLUE = '\033[44m'
    BMAGENTA = '\033[45m'
    BCYAN = '\033[46m'
    BGRAY = '\033[47m'

    END = '\033[0m'
    BOLD = '\033[1m'
    ITALIC = '\033[3m'


# Decorator to run a function in a separate thread
def nonblocking(static_identifier: str = None):
    """
    A decorator.
    A wrapped function when called will run in a separate thread.
    :param str static_identifier: An identifier used to name the thread. If None, the wrapped function will require a
    thread identifier as first argument.
    :return: the wrapped function
    :rtype: callable
    """
    def dynamic_nonblocking(func):
        def wrapper(thread_identifier, *args, **kwargs):
            thread = threading.Thread(target=func, args=args, kwargs=kwargs, name=thread_identifier)
            thread.start()

        return wrapper

    def static_nonblocking(func):
        def wrapper(*args, **kwargs):
            thread = threading.Thread(target=func, args=args, kwargs=kwargs, name=static_identifier)
            thread.start()

        return wrapper

    return dynamic_nonblocking if static_identifier is None else static_nonblocking


# Base exception for the engine
class KXException(Exception):
    """
    Main and generic exception used by KuiX.
    Used by the logger, contains a custom traceback.
    """

    def __init__(self, exception: Exception, traceback: str = None):
        """
        Instance a KXException from an exception.
        :param Exception exception: the caught exception
        :param traceback: an optional traceback message to be added to the custom traceback
        """
        self.type = type(exception).__name__
        self.message = str(exception)
        self.messages_traceback = [traceback] if traceback is not None else []
        self.traceback = tba.format_exc()

    def add_traceback(self, message: str):
        """
        Add a message to a custom traceback.
        :param str message:
        """
        self.messages_traceback.append(message)
