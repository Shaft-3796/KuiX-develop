"""
Contains all the exceptions used in the project.
"""
import traceback as tba


def cast(e, e_type=None):
    """
    Casts an exception to a GenericException if it is not already one.
    :param e_type: type of the return exception
    :param e: the exception to cast
    :return: the cast exception
    """
    return e if isinstance(e, GenericException) else (GenericException(e) if e_type is None else e_type(e))

def serialize(e):
    return {"traceback": e.traceback, "notes": e.notes, "type": type(e).__name__}

def deserialize(e: dict):
    _e = globals()[e["type"]]()
    _e.traceback = e["traceback"]
    _e.notes = e["notes"]
    return _e

class GenericException(BaseException):

    def __init__(self, exception: BaseException = None, message: str = "An error occurred"):

        super().__init__(message)
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

# --- PROCESS ---

class KxProcessStrategyImportError(GenericException):
    pass

class StrategyNotFoundError(GenericException):
    pass

class WorkerAlreadyExistsError(GenericException):
    pass

class WorkerNotFoundError(GenericException):
    pass

class WorkerInitError(GenericException):
    pass

class WorkerMethodCallError(GenericException):
    pass