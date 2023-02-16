"""
Contains all the exceptions used in the project.
"""
import traceback as tba


def cast(e):
    """
    Casts an exception to a GenericException if it is not already one.
    :param e: the exception to cast
    :return: the cast exception
    """
    return e if isinstance(e, GenericException) else GenericException(e)

class GenericException(BaseException):

    def __init__(self, exception: BaseException = None):
        self.traceback = tba.format_exc()
        self.notes = [str(exception)] if exception is not None else []

    def add_note(self, note: str):
        self.notes.append(note)
        return self


# --- SOCKET EXCEPTIONS ---

# Server
class SocketServerBindError(GenericException):
    pass

class SocketServerAcceptError(GenericException):
    pass

class SocketServerListeningConnectionError(GenericException):
    pass

class SocketServerCliIdentifierNotFound(GenericException):
    pass

class SocketServerSendError(GenericException):
    pass

class SocketServerCloseError(GenericException):
    pass

class SocketServerEventCallbackError(GenericException):
    pass

# Client
class SocketClientConnectionError(GenericException):
    pass

class SocketClientListeningError(GenericException):
    pass

class SocketClientSendError(GenericException):
    pass

class SocketClientCloseError(GenericException):
    pass

class SocketClientEventCallbackError(GenericException):
    pass

# --- IPC ---

# Server
class IpcServerRequestHandlerError(GenericException):
    pass

# Client
class IpcClientRequestHandlerError(GenericException):
    pass