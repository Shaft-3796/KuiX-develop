from src.core.networking.SocketClient import SocketClient
from src.core.Logger import LOGGER, KX_PROCESS
from src.core.Exceptions import *
import threading
import time
import uuid

# Request types
FIRE_AND_FORGET = "FIRE_AND_FORGET"
BLOCKING = "BLOCKING"
RESPONSE = "RESPONSE"

class IpcClient(SocketClient):

    def __init__(self, identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):
        """
        Instance an ipc client used for inter process communication (IPC).
        This client extends the SocketClient class and add the ability to register endpoints and send requests to them.
        :param identifier: The identifier of the client.
        :param auth_key: The key to authenticate the client.
        :param port: The port to connect on. Default is 6969.
        :param host: The host to connect  on. Default is localhost.
        :param artificial_latency: Time in s between each .recv call for a connection. Default is 0.1s. This is used to
        prevent the CPU from being overloaded. Change this value if you know what you're doing.

        :raise SocketClientConnectionError: If the client failed to connect to the server, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        # Super call
        super().__init__(identifier, auth_key, host, port, artificial_latency)
        try:
            self.connect()
        except SocketClientConnectionError as e:
            raise e.add_ctx(f"Ipc Client '{identifier}': failed to connect to {host}:{port}, look at the initial "
                            f"exception for more details.")

        # Placeholder for endpoints
        self.endpoints = {}  # type dict[str, Callable]
        self.blocking_endpoints = {}  # type dict[str, Callable]

        # Placeholder for blocking requests
        self.blocking_requests = {}  # type dict[str: id, list [semaphore, response]]

        # Events
        self.register_on_message_received(self.handle_request)

    # Requests handler, triggered when a message is received
    def handle_request(self, identifier: str, data: dict):
        """
        Handle a request received from the server.
        Automatically called when a message is received.
        :param identifier: identifier of the client (same as self.identifier)
        :param data: The data received from the server as a dict.
        """
        try:
            # Fire and forget or blocking request
            if data["rtype"] == FIRE_AND_FORGET or data["rtype"] == BLOCKING:
                ep = self.endpoints if data["rtype"] == FIRE_AND_FORGET else self.blocking_endpoints
                if data["endpoint"] not in ep:
                    if data["rtype"] == BLOCKING:
                        e = UnknownEndpoint(f"IPC Client {identifier}: received a request to '{data['endpoint']}' "
                                            f"but this endpoint"
                                            f" is not registered as a blocking endpoint !\nWarning, because this "
                                            f"endpoint is a blocking endpoint, this will lead to an infinite function\n"
                                            f"call with unexpected behavior and performances issues")
                        LOGGER.error_exception(e, KX_PROCESS)
                    if data["rtype"] == FIRE_AND_FORGET:
                        e = UnknownEndpoint(f"IPC Client {identifier}: received a request to '{data['endpoint']} "
                                            f"but this endpoint is not registered !")
                        LOGGER.error_exception(e, KX_PROCESS)
                    return

                ep[data["endpoint"]](data["data"]) if data["rtype"] == FIRE_AND_FORGET \
                    else ep[data["endpoint"]](data["rid"], data["data"])

            # Response request
            elif data["rtype"] == RESPONSE:
                for i in range(2):
                    if data["rid"] not in self.blocking_requests:
                        time.sleep(0.2)
                if data["rid"] not in self.blocking_requests:
                    e = UnknownRid(f"IPC Client {identifier}: received a response to a request with an unknown rid.\n"
                                   f"When the client send a blocking request, it add a field 'rid' to the request, \n"
                                   f"when the server response through the 'send_response' method, the same rid have \n"
                                   f"to be included int the response request.\n This error will lead to an infinite "
                                   f"function call and unexpected behavior.")
                    LOGGER.error_exception(e, KX_PROCESS)
                    return
                self.blocking_requests[data["rid"]][1] = data["data"]
                self.blocking_requests[data["rid"]][0].release()

            # Unknown request type
            else:
                e = UnknownRequestType(f"IPC Client {identifier}: received unknown request type: '{data['rtype']}'.\n"
                                       f"Only 'FIRE_AND_FORGET', 'BLOCKING' and 'RESPONSE' are allowed.")
                LOGGER.error_exception(e, KX_PROCESS)

        except KeyError as e:
            LOGGER.error_exception(IpcClientRequestHandlerError(f"IPC Client '{identifier}': error while handling a "
                                                                f"request from server.\n"
                                                                f"A field is missing in your request !\n"
                                                                f"Request: {data}, \n"
                                                                f"look at the initial exception for more details.") + e,
                                   KX_PROCESS)
        except Exception as e:
            LOGGER.error_exception(IpcClientRequestHandlerError(f"IPC Client '{identifier}': error while "
                                                                f"handling a request from server.'\n"
                                                                f"Request: {data}, "
                                                                f"look at the initial exception for more details.") + e,
                                   KX_PROCESS)

    # --- Sending ---

    # Fire and forget
    def send_fire_and_forget_request(self, endpoint: str, data: dict):
        """
        Send data through a fire and forget request to the server.
        This method will directly return after sending the request.
        :param endpoint: endpoint as a str, this endpoint must be registered.
        :param data: data to send as a dict.

        :raise SocketClientSendError: If the client failed to send the request, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        try:
            self.send_data({"rtype": FIRE_AND_FORGET, "endpoint": endpoint, "data": data})
        except SocketClientSendError as e:
            raise e.add_ctx(f"Ipc Client '{self.identifier}: error while sending a fire and forget "
                            f"request to server', "
                            f"endpoint '{endpoint}'\nData: {data}")

    # blocking request
    def send_blocking_request(self, endpoint: str, data: dict):
        """
        Send data through a blocking request to the server.
        This method will block until the server send the response.
        Warning, if the server doesn't send the response, this method will block forever.
        Be sure to register the endpoint on the server side with a correct response.
        :param endpoint: endpoint as a str, this endpoint must be registered.
        :param data: data to send as a dict.

        :raise SocketClientSendError: If the client failed to send the request, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        # Create a unique id for the request
        rid = str(uuid.uuid4())
        # Create a locked semaphore
        semaphore = threading.Semaphore(0)
        # Create a placeholder for the response
        response = None
        # Fill the response placeholder
        self.blocking_requests[rid] = [semaphore, response]
        # Send the request
        try:
            self.send_data({"rtype": BLOCKING, "endpoint": endpoint, "data": data, "rid": rid})
        except SocketClientSendError as e:
            raise e.add_ctx(f"Ipc Client '{self.identifier}: error while sending a blocking "
                            f"request to server', "
                            f"endpoint '{endpoint}'\nData: {data}")
        # Wait for the response
        semaphore.acquire()
        # Return the response
        resp = self.blocking_requests[rid][1]
        del self.blocking_requests[rid]
        return resp

    # responses
    def send_response(self, endpoint: str, data: dict, rid: str):
        """
        Send response to a blocking request to the server.
        This method will directly return after sending the response.
        :param endpoint: endpoint as a str.
        :param data: data to send as a dict.
        :param rid: request id as a str, this id must be the same as the one received in the initial blocking request.

        :raise SocketClientSendError: If the client failed to send the request, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        try:
            self.send_data({"rtype": RESPONSE, "endpoint": endpoint, "data": data, "rid": rid})
        except SocketClientSendError as e:
            raise e.add_ctx(f"Ipc Client '{self.identifier}: error while sending a response "
                            f"request to server', "
                            f"endpoint '{endpoint}'\nData: {data}")
