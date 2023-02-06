import threading
from dataclasses import dataclass
import traceback as tba

# For socket communication
EOF = "04"


# Terminal colors
@dataclass
class C:
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
def nonblocking(static_identifier=None):
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
class KXTException(Exception):

    def __init__(self, exception: Exception, traceback: str = None):
        self.type = type(exception).__name__
        self.message = str(exception)
        self.messages_traceback = [traceback] if traceback is not None else []
        self.traceback = tba.format_exc()

    def add_traceback(self, message: str):
        self.messages_traceback.append(message)
