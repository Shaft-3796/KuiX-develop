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
"""
import threading
import time
import uuid

from src.core.networking.SocketServer import SocketServer
from src.core.Utils import endpoint
from src.core.Logger import LOGGER, CORE

# Request types
FIRE_AND_FORGET = "FIRE_AND_FORGET"
BLOCKING = "BLOCKING"
RESPONSE = "RESPONSE"


class IpcServer(SocketServer):

    def __init__(self, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):
        # Super call
        super().__init__(auth_key, host, port, artificial_latency)

        # Placeholder for endpoints
        self.endpoints = {}  # type dict[str, Callable]
        # Iterating over methods:
        for method in [getattr(self, method_name) for method_name in dir(self)
                       if callable(getattr(self, method_name))]:
            if hasattr(method, "api_endpoint"):
                self.endpoints[getattr(method, "api_endpoint")] = method

        # Placeholder for blocking requests
        self.blocking_requests = {}  # type dict[str: id, list [semaphore, response]]

        # Events
        self.register_on_message_received(self.handle_request)

    # Requests handler, triggered when a message is received
    def handle_request(self, identifier: str, request: dict):
        try:
            # Fire and forget request
            if request["rtype"] == FIRE_AND_FORGET:
                if request["endpoint"] not in self.endpoints:
                    LOGGER.warning(f"IPC Server: received unknown endpoint '{request['endpoint']}' from {identifier}",
                                   CORE)
                    return
                self.endpoints[request["endpoint"]](identifier, request["data"])

            # Blocking request
            elif request["rtype"] == BLOCKING:
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

        except Exception as e:
            LOGGER.error(f"IPC Server: error while handling request from {identifier}: {e}", CORE)

    # --- Endpoints ---
    @endpoint("ping")
    def ping(self, identifier: str, request: dict):
        LOGGER.trace(f"IPC Server {identifier} : ping received from {identifier}", CORE)

    @endpoint("blocking_ping")
    def blocking_ping(self, identifier: str, request: dict):
        LOGGER.trace(f"IPC Server {identifier} : blocking ping received from {identifier}", CORE)
        self.send_fire_and_forget_request(identifier, {"rtype": FIRE_AND_FORGET, "data": "pong", "endpoint": request["endpoint"], "rid": request["rid"]})
        # TODO: bien redef les types de requetes pour ne pas s'enmeler avev les reponses et les envoies.

    # --- Sending ---

    # Fire and forget
    def send_fire_and_forget_request(self, identifier: str, data: dict):
        try:
            self.send_data(identifier, {"rtype": FIRE_AND_FORGET, "data": data})
        except Exception as e:
            e.add_traceback("IpcServer, send fire and forget")
            raise e

    # blocking request
    def send_blocking_request(self, identifier: str, data: dict):
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
            self.send_data(identifier, {"rtype": BLOCKING, "data": data, "rid": rid})
            # Wait for the response
            semaphore.acquire()
            # Return the response
            return self.blocking_requests[rid][1]
        except Exception as e:
            e.add_traceback("IpcServer, send blocking request")
            raise e

