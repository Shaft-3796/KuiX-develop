from src.core.networking.SocketServer import SocketServer
from src.core.Logger import LOGGER, CORE
from src.core.Exceptions import *
import threading
import time
import uuid

# Request types
FIRE_AND_FORGET = "FIRE_AND_FORGET"
BLOCKING = "BLOCKING"
RESPONSE = "RESPONSE"


class IpcServer(SocketServer):

    def __init__(self, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):
        """
                Instance an ipc server used for inter process communication (IPC).
                This server extends the SocketServer class and add the ability to register endpoints and send
                requests to them.
                :param auth_key: The key to authenticate clients.
                :param port (optional): The port to connect on. Default is 6969.
                :param host (optional): The host to connect  on. Default is localhost.
                :param artificial_latency (optional): Time in s between each .recv call for a connection. Default is 0.1s.
                This is used to prevent the CPU from being overloaded. Change this value if you know what you're doing.

                Communication protocol:

                I-) FireAndForget request:
                1) Client or server sends a request to an endpoint of the other party.
                2) Client or server returns directly after sending the request.
                3) The other party processes the request and can send another request if necessary.
                request = {rtype: "FIRE_AND_FORGET", endpoint: "endpoint", data: {...}}

                II-) Blocking request:
                1) Client or server sends a request to an endpoint of the other party, the sender add a unique id to the request.
                2) Client or server locks on a new semaphore.
                3) The other party processes the request and send the response with a "rid" field.
                4) Client or server socket threads unlock the semaphore.
                5) Client or server request call unlocks and return the response
                request = {rtype: "BLOCKING", endpoint: "endpoint", data: {...}, rid: "unique_id"}

                III-) Response:
                1) Other party receives a blocking request on an endpoint.
                2) Other party processes the request and send the response as a RESPONSE request with a "rid" field.
                3) Client or server receives the response, save it, and release the lock.
                4) Client or server initial blocking request call return the response.
                request = {rtype: "RESPONSE", endpoint: "endpoint", data: {...}, rid: "unique_id"}

                :raise SocketServerBindError: If the server fails to bind to the specified host and port.
                """
        # Super call
        try:
            super().__init__(auth_key, host, port, artificial_latency)
        except SocketServerBindError as e:
            raise e.add_ctx("Ipc Server setup failed")

        # Placeholder for endpoints
        self.endpoints = {}  # type dict[str, Callable]
        self.blocking_endpoints = {}  # type dict[str, Callable]

        # Placeholder for blocking requests
        self.blocking_requests = {}  # type dict[str: id, list [semaphore, response]]

        # Super Call
        self.register_on_message_received(self.handle_request)

    # Requests handler, triggered when a message is received
    def handle_request(self, identifier: str, data: dict):
        """
        Handle a request received from a client.
        Automatically called when a message is received.
        :param identifier: identifier of the client.
        :param data: The data received from the client as a dict.
        """
        try:
            # Fire and forget or blocking request
            if data["rtype"] == FIRE_AND_FORGET or data["rtype"] == BLOCKING:
                ep = self.endpoints if data["rtype"] == FIRE_AND_FORGET else self.blocking_endpoints
                if data["endpoint"] not in ep:
                    LOGGER.warning(f"IPC Server: received unknown endpoint '{data['endpoint']}'\n-> "
                                   f"If the request was a blocking request, this error will lead to an infinite "
                                   f"function call !'",
                                   CORE)
                    return
                ep[data["endpoint"]](identifier, data["data"]) if data["rtype"] == FIRE_AND_FORGET \
                    else ep[data["endpoint"]](identifier, data["rid"], data["data"])

            # Response request
            elif data["rtype"] == RESPONSE:
                for i in range(2):
                    if data["rid"] not in self.blocking_requests:
                        time.sleep(0.2)
                if data["rid"] not in self.blocking_requests:
                    LOGGER.warning(f"IPC Server: received unknown rid, endpoint '{data['endpoint']}' from "
                                   f"{identifier}\nRequest: {data}", CORE)
                    return
                self.blocking_requests[data["rid"]][1] = data["data"]
                self.blocking_requests[data["rid"]][0].release()

            # Unknown request type
            else:
                LOGGER.warning(f"IPC Server: received unknown request type: {data['rtype']} from {identifier}",
                               CORE)

        except Exception as e:
            LOGGER.error_exception(IpcServerRequestHandlerError(f"Ipc Server: error while handling a "
                                                                f"request from client '{identifier}, "
                                                                f"look at the initial exception for more details.'\n"
                                                                f"Request: {data}") + e, CORE)

    # --- Sending ---

    # Fire and forget
    def send_fire_and_forget_request(self, identifier: str, endpoint: str, data: dict):
        """
        Send data through a fire and forget request to a client.
        This method will directly return after sending the request.
        :param identifier: identifier of the client.
        :param endpoint: endpoint as a str, this endpoint must be registered.
        :param data: data to send as a dict.

        :raise ClientIdentifierNotFound: If the client is not found. This can happen if the client is not connected
        or is the identifier is wrong.
        :raise SocketServerSendError: If the server fails to send the data, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        try:
            self.send_data(identifier, {"rtype": FIRE_AND_FORGET, "endpoint": endpoint, "data": data})
        except SocketServerClientNotFound as e:
            e = ClientIdentifierNotFoundError(f"Client identifier '{identifier}' is wrong, "
                                              f"or client is not connected.") + e
            raise e.add_ctx(f"Ipc Server: error while sending a fire and forget "
                            f"request, identifier not found,\n "
                            f"request to client '{identifier}',\n "
                            f"endpoint '{endpoint}',\nData: {data}")
        except SocketServerSendError as e:
            raise e.add_ctx(f"Ipc Server: error while sending a fire and forget "
                            f"request, identifier not found,\n "
                            f"request to client '{identifier}',\n "
                            f"endpoint '{endpoint}',\nData: {data}")

    # blocking request
    def send_blocking_request(self, identifier: str, endpoint: str, data: dict):
        """
        Send data through a blocking request to a client.
        This method will block until the server send the response.
        Warning, if the server doesn't send the response, this method will block forever.
        Be sure to register the endpoint on the client side with a correct response.
        :param identifier: identifier of the client.
        :param endpoint: endpoint as a str, this endpoint must be registered.
        :param data: data to send as a dict.

        :raise ClientIdentifierNotFound: If the client is not found. This can happen if the client is not connected
        or is the identifier is wrong.
        :raise SocketServerSendError: If the server fails to send the data, you can access the initial
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
            self.send_data(identifier, {"rtype": BLOCKING, "endpoint": endpoint, "data": data, "rid": rid})
        except SocketServerClientNotFound as e:
            e = ClientIdentifierNotFoundError(f"Client identifier '{identifier}' is wrong, "
                                              f"or client is not connected.") + e
            raise e.add_ctx(f"Ipc Server: error while sending a blocking"
                            f"request, identifier not found,\n "
                            f"request to client '{identifier}',\n "
                            f"endpoint '{endpoint}',\nData: {data}")
        except SocketServerSendError as e:
            raise e.add_ctx(f"Ipc Server: error while sending a fire and forget "
                            f"request, identifier not found,\n "
                            f"request to client '{identifier}',\n "
                            f"endpoint '{endpoint}',\nData: {data}")
        # Wait for the response
        semaphore.acquire()
        # Return the response
        resp = self.blocking_requests[rid][1]
        del self.blocking_requests[rid]
        return resp

    # responses
    def send_response(self, identifier: str, endpoint: str, data: dict, rid: str):
        """
        Send response to a blocking request to a client.
        This method will directly return after sending the response.
        :param identifier: identifier of the client.
        :param endpoint: endpoint as a str.
        :param data: data to send as a dict.
        :param rid: request id as a str, this id must be the same as the one received in the initial blocking request.

        :raise ClientIdentifierNotFound: If the client is not found. This can happen if the client is not connected
        or is the identifier is wrong.
        :raise SocketServerSendError: If the server fails to send the data, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        try:
            self.send_data(identifier, {"rtype": RESPONSE, "endpoint": endpoint, "data": data, "rid": rid})
        except SocketServerClientNotFound as e:
            e = ClientIdentifierNotFoundError(f"Client identifier '{identifier}' is wrong, "
                                              f"or client is not connected.") + e
            raise e.add_ctx(f"Ipc Server: error while sending a response"
                            f"request, identifier not found,\n "
                            f"request to client '{identifier}',\n "
                            f"endpoint '{endpoint}',\nData: {data}")
        except SocketServerSendError as e:
            raise e.add_ctx(f"Ipc Server: error while sending a response"
                            f"request, identifier not found,\n "
                            f"request to client '{identifier}',\n "
                            f"endpoint '{endpoint}',\nData: {data}")

# TODO: add register endpoint method.
# TODO tell how to register endpoint when unknown endpoint is received, convert this to an error.