"""
This module implements an IPC server using sockets.

Communication protocol:

I-) FireAndForget request:
    1) Client or server sends a request to an endpoint of the other party.
    2) Client or server returns directly after sending the request.
    3) The other party processes the request and can send another request if necessary.
    request = {rtype: "FIRE_AND_FORGET", endpoint: "endpoint", data: {...}}

II-) Blocking request:
    1) Client or server sends a request to an endpoint of the other party, the sender add a unique id to the request.
    2) Client or server locks on a new semaphore.
    3) The other party processes the request and send the response on the id as endpoint.
    4) Client or server socket threads unlock the semaphore.
    5) Client or server request call unlocks and return the response
    request = {rtype: "BLOCKING", endpoint: "endpoint", data: {...}, rid: "unique_id"}

III-) Response:
    1) Other party receives a blocking request on an endpoint.
    2) Other party processes the request and send the response as a RESPONSE request with a "rid" field.
    3) Client or server receives the response, save it, and release the lock.
    4) Client or server initial blocking request call return the response.
    request = {rtype: "RESPONSE", endpoint: "endpoint", data: {...}, rid: "unique_id"}
"""
from src.core.networking.SocketServer import SocketServer
from src.core.Utils import Endpoint, BlockingEndpoint
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
        # Super call
        try:
            super().__init__(auth_key, host, port, artificial_latency)
        except SocketServerBindError as e:
            raise e.add_note("Ipc Server setup failed")
        self.accept_new_connections()

        # Placeholder for endpoints
        self.endpoints = {}  # type dict[str, Callable]
        self.blocking_endpoints = {}  # type dict[str, Callable]

        # Placeholder for blocking requests
        self.blocking_requests = {}  # type dict[str: id, list [semaphore, response]]

        # Super Call
        self.register_on_message_received(self.handle_request)

    # Requests handler, triggered when a message is received
    def handle_request(self, identifier: str, request: dict):
        try:
            # Fire and forget or blocking request
            if request["rtype"] == FIRE_AND_FORGET or request["rtype"] == BLOCKING:
                ep = self.endpoints if request["rtype"] == FIRE_AND_FORGET else self.blocking_endpoints
                if request["endpoint"] not in ep:
                    LOGGER.warning(f"IPC Server: received unknown endpoint '{request['endpoint']}' from {identifier}",
                                   CORE)
                    return
                ep[request["endpoint"]](identifier, request["data"]) if request["rtype"] == FIRE_AND_FORGET \
                    else ep[request["endpoint"]](identifier, request["rid"], request["data"])

            # Response request
            elif request["rtype"] == RESPONSE:
                for i in range(2):
                    if request["rid"] not in self.blocking_requests:
                        time.sleep(0.2)
                if request["rid"] not in self.blocking_requests:
                    LOGGER.warning(f"IPC Server: received unknown rid, endpoint '{request['endpoint']}' from "
                                   f"{identifier}\nRequest: {request}", CORE)
                    return
                self.blocking_requests[request["rid"]][1] = request["data"]
                self.blocking_requests[request["rid"]][0].release()

            # Unknown request type
            else:
                LOGGER.warning(f"IPC Server: received unknown request type: {request['rtype']} from {identifier}",
                               CORE)

        except BaseException as e:
            LOGGER.error_exception(IpcServerRequestHandlerError(e).add_note(f"Ipc Server: error while handling a "
                                                                            f"request from client '{identifier}'\n"
                                                                            f"Request: {request}"), CORE)

    # --- Sending ---

    # Fire and forget
    def send_fire_and_forget_request(self, identifier: str, endpoint: str, data: dict):
        try:
            self.send_data(identifier, {"rtype": FIRE_AND_FORGET, "endpoint": endpoint, "data": data})
        except SocketServerCliIdentifierNotFound as e:
            raise e.add_note(f"Ipc Server: error while sending a fire and forget "
                             f"request, identifier not found, "
                             f"request to client '{identifier}', "
                             f"endpoint '{endpoint}'\nData: {data}")
        except SocketServerSendError as e:
            raise e.add_note(f"Ipc Server: error while sending a fire and forget "
                             f"request to client '{identifier}', "
                             f"endpoint '{endpoint}'\nData: {data}")

    # blocking request
    def send_blocking_request(self, identifier: str, endpoint: str, data: dict):
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
        except SocketServerCliIdentifierNotFound as e:
            raise e.add_note(f"Ipc Server: error while sending a blocking request, "
                             f"identifier not found, "
                             f"request to client '{identifier}', "
                             f"endpoint '{endpoint}'\nData: {data}")
        except SocketServerSendError as e:
            raise e.add_note(f"Ipc Server: error while sending a blocking "
                             f"request to client '{identifier}', "
                             f"endpoint '{endpoint}'\nData: {data}")
        # Wait for the response
        semaphore.acquire()
        # Return the response
        resp = self.blocking_requests[rid][1]
        del self.blocking_requests[rid]
        return resp

    # responses
    def send_response(self, identifier: str, endpoint: str, data: dict, rid: str):
        try:
            self.send_data(identifier, {"rtype": RESPONSE, "endpoint": endpoint, "data": data, "rid": rid})
        except SocketServerCliIdentifierNotFound as e:
            raise e.add_note(f"Ipc Server: error while sending a response request, "
                             f"identifier not found, "
                             f"request to client '{identifier}', "
                             f"endpoint '{endpoint}'\nData: {data}")
        except SocketServerSendError as e:
            raise e.add_note(f"Ipc Server: error while sending a response "
                             f"request to client '{identifier}', "
                             f"endpoint '{endpoint}'\nData: {data}")
