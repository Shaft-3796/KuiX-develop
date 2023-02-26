"""
Contains all the exceptions used in the project.
"""
import traceback
import traceback as tba

# TODO, If a GenericException or child is instanced from an Exception without a message an error will be raised.

def cast(e, e_type=None):
    """
    Casts an exception to a GenericException if it is not already one.
    :param e_type: type of the return exception
    :param e: the exception to cast
    :return: the cast exception
    """
    return e if isinstance(e, GenericException) else (GenericException(e) if e_type is None else e_type(e))


def deserialize(e: dict):
    _e = globals()[e["type"]](Exception(""))
    _e.base_msg = e["base_msg"]
    _e.traceback = e["traceback"]
    _e.context = e["context"]
    return _e


class GenericException(Exception):
    def __init__(self, exception: Exception):
        """
        :param exception: Last exception d.
        """
        # If the exception is a GenericException
        if isinstance(exception, GenericException):
            self.base_msg = exception.base_msg
            self.traceback = exception.traceback
            self.context = exception.context
        # If the exception is a native/raw except
        elif isinstance(exception, Exception):
            self.base_msg = exception.args[0]
            self.traceback = traceback.format_exc()
            self.context = []

    def add_ctx(self, context: str):
        self.context.append(context)
        return self

    def __str__(self):
        return self.base_msg

    def serialize(self):
        return {"traceback": self.traceback, "context": self.context, "type": type(self).__name__,
                "base_msg": self.base_msg}


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


class StrategyNotFoundError(Exception):
    pass


class WorkerAlreadyExistsError(Exception):
    pass


class WorkerNotFoundError(Exception):
    pass


class WorkerInitError(GenericException):
    pass


class WorkerMethodCallError(GenericException):
    pass


# --- Strategy & strategy components ---
class StrategyComponentOpeningError(GenericException):
    pass

class StrategyComponentStartingError(GenericException):
    pass

class StrategyComponentStoppingError(GenericException):
    pass

class StrategyComponentClosingError(GenericException):
    pass

class WorkerAlreadyStarted(Exception):
    pass

class WorkerAlreadyStopped(Exception):
    pass

class WorkerStoppingTimeout(Exception):
    pass

class WorkerStoppingError(GenericException):
    pass

class StrategyClosingError(GenericException):
    pass

# --- Core ---
class CoreSetupError(GenericException):
    pass

class CoreNotConfigured(Exception):
    pass

class ProcessAlreadyExists(Exception):
    pass

class StrategyAlreadyRegistered(Exception):
    pass

class StrategyNotRegistered(Exception):
    pass