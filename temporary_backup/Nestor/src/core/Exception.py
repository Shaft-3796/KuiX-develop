"""
Exceptions.py
This files centralizes all the exceptions used in the project.
"""
import traceback as tba

# Exchange connectors
class NestorException(Exception):

    def __init__(self, exception: Exception, traceback: str = None):
        self.type = type(exception).__name__
        self.message = str(exception)
        self.messages_traceback = [traceback] if traceback is not None else []
        self.traceback = tba.format_exc()

    def add_traceback(self, message: str):
        self.messages_traceback.append(message)


def raise_exception(exception: Exception, message: str = None):
    if type(exception) == NestorException:
        exception.add_traceback(message)
        raise exception
    else:
        raise NestorException(exception, message)
