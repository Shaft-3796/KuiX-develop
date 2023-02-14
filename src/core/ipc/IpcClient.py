"""
This module implements an IPC client using sockets.

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
"""
from src.core.networking.SocketClient import SocketClient
from src.core.Utils import Endpoint, BlockingEndpoint
from src.core.Logger import LOGGER, CORE
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
        # Super call
        super().__init__(identifier, auth_key, host, port, artificial_latency)
        try:
            self.connect()
        except Exception as e:
            # KXException
            raise e

        # Placeholder for endpoints
        self.endpoints = {}  # type dict[str, Callable]
        self.blocking_endpoints = {}  # type dict[str, Callable]
        # Iterating over methods:
        for method in [getattr(self, method_name) for method_name in dir(self)
                       if callable(getattr(self, method_name))]:
            if hasattr(method, "faf_endpoint"):
                self.endpoints[getattr(method, "faf_endpoint")] = method
            if hasattr(method, "blocking_endpoint"):
                self.blocking_endpoints[getattr(method, "blocking_endpoint")] = method

        # Placeholder for blocking requests
        self.blocking_requests = {}  # type dict[str: id, list [semaphore, response]]

        # Events
        self.register_on_message_received(self.handle_request)

    # Requests handler, triggered when a message is received
    def handle_request(self, identifier: str, request: dict):
        try:
            # Fire and forget or blocking request
            if request["rtype"] == FIRE_AND_FORGET or request["rtype"] == BLOCKING:
                ep = self.endpoints if request["rtype"] == FIRE_AND_FORGET else self.blocking_endpoints
                if request["endpoint"] not in ep:
                    LOGGER.warning(f"IPC Client {identifier}: received unknown endpoint '{request['endpoint']}'",
                                   CORE)
                    return
                ep[request["endpoint"]](request["data"]) if request["rtype"] == FIRE_AND_FORGET \
                    else ep[request["endpoint"]](request["rid"], request["data"])

            # Response request
            elif request["rtype"] == RESPONSE:
                for i in range(2):
                    if request["rid"] not in self.blocking_requests:
                        time.sleep(0.2)
                if request["rid"] not in self.blocking_requests:
                    LOGGER.warning(f"IPC Client {identifier}: received unknown rid, endpoint '{request['endpoint']}'"
                                   f"\nRequest: {request}", CORE)
                    return
                self.blocking_requests[request["rid"]][1] = request["data"]
                self.blocking_requests[request["rid"]][0].release()

            # Unknown request type
            else:
                LOGGER.warning(f"IPC Client {identifier}: received unknown request type: {request['rtype']}",
                               CORE)

        except Exception as e:
            LOGGER.error(f"IPC Client {identifier}: error while handling request: {e}", CORE)

    # --- Endpoints ---
    @Endpoint("ping")
    def ping(self, request: dict):
        LOGGER.trace(f"IPC Client {self.identifier}: ping received", CORE)

    # --- Blocking endpoints ---
    @BlockingEndpoint("blocking_ping")
    def blocking_ping(self, rid: str, request: dict):
        LOGGER.trace(f"IPC Client {self.identifier}: blocking ping received", CORE)
        self.send_response("blocking_ping", {"response": "pong"}, rid)

    # --- Sending ---

    # Fire and forget
    def send_fire_and_forget_request(self, endpoint: str, data: dict):
        try:
            self.send_data({"rtype": FIRE_AND_FORGET, "endpoint": endpoint, "data": data})
        except Exception as e:
            e.add_traceback("IpcClient, send fire and forget")
            raise e

    # blocking request
    def send_blocking_request(self, endpoint: str, data: dict):
        try:
            # Create a unique id for the request
            rid = str(uuid.uuid4())
            # Create a locked semaphore
            semaphore = threading.Semaphore(0)
            # Create a placeholder for the response
            response = None
            # Fill the response placeholder
            self.blocking_requests[rid] = [semaphore, response]
            # Send the request
            self.send_data({"rtype": BLOCKING, "endpoint": endpoint, "data": data, "rid": rid})
            # Wait for the response
            semaphore.acquire()
            # Return the response
            resp = self.blocking_requests[rid][1]
            del self.blocking_requests[rid]
            return resp
        except Exception as e:
            e.add_traceback("IpcClient, send blocking request")
            raise e

    # responses
    def send_response(self, endpoint: str, data: dict, rid: str):
        try:
            self.send_data({"rtype": RESPONSE, "endpoint": endpoint, "data": data, "rid": rid})
        except Exception as e:
            e.add_traceback("IpcClient, send response")
            raise e


