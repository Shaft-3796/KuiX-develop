"""
This module implements an IPC custom protocol using sockets.
"""
import select
import threading

from src.core.Exceptions import *
from src.core.Logger import LOGGER, CORE
from src.core.Utils import EOT, IGNORE
import socket
import json
import time


class SocketClient:
    """
    Implementation of a custom socket client used for IPC (Inter Process Communication).

    Methods:
        __init__(identifier, auth_key, host, port, artificial_latency)
        Instance the server socket, do not raise any exception.

        connect()

    """

    # Constructor
    def __init__(self, identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):
        """
        Instance a socket client used for inter process communication (IPC).
        :param identifier: The identifier of the client.
        :param auth_key: The key to authenticate the client.
        :param port (optional): The port to connect on. Default is 6969.
        :param host (optional): The host to connect  on. Default is localhost.
        :param artificial_latency (optional): Time in s between each .recv call for a connection. Default is 0.1s.
        This is used to prevent the CPU from being overloaded. Change this value if you know what you're doing.
        """
        # Args
        self.identifier = identifier
        self.auth_key = auth_key
        self.host = host
        self.port = port
        self.artificial_latency = artificial_latency

        # Events
        self.on_connection_accepted = [lambda _identifier: threading.Thread(target=self.listen_for_connection,
                                                                            name=_identifier).start()]
        self.on_connection_refused = []
        self.on_connection_closed = []
        self.on_client_closed = []
        self.on_message_received = []
        self.on_message_sent = []

        # Socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(5)

        # To close the IPC client
        self.ipc_client_closed = False

        LOGGER.trace(f"Socket Client {self.identifier} : client fully instanced and ready to connect on "
                     f"{self.host}:{self.port}", CORE)

    # --- Low level methods ---

    # Connect to the server
    def connect(self):
        """
        Connects the client to the server.

        :raises SocketClientConnectionError: If the client failed to connect to the server, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        try:
            # Accept connection
            self.socket.connect((self.host, self.port))
            LOGGER.trace(f"IPC Client {self.identifier} : connected to the server, sending auth request", CORE)

            # Authentication
            authentication_payload = {"identifier": self.identifier, "key": self.auth_key}
            self.socket.sendall(json.dumps(authentication_payload).encode("utf-8"))

            # Wait for response
            data = json.loads(self.socket.recv(1024).decode("utf-8"))

            if data["status"] == "valid":
                # Connection validated
                LOGGER.trace(f"IPC Client {self.identifier} : Server validated creds.", CORE)
                self.__trigger__(self.on_connection_accepted, identifier=authentication_payload["identifier"])
            else:
                LOGGER.trace(f"IPC Client {self.identifier}: Server invalidated creds: ", CORE)
                self.__trigger__(self.on_connection_refused, identifier=authentication_payload["identifier"])
        except Exception as e:
            raise SocketClientConnectionError(f"Socket Client '{self.identifier}' failed to connect "
                                              f"to server on {self.host}:{self.port}, look at the initial exception "
                                              f"for more details.") + e

    # Blocking call, handle requests from the server
    def listen_for_connection(self):
        """
        Listens the server connection, trigger the on_message_received event when a message is received.
        This method is blocking and called automatically when the connection is accepted by the server.
        """

        def flush_buffer():
            nonlocal buffer
            LOGGER.trace(f"IPC Client  {self.identifier} : Flushing buffer, buffer: {buffer}", CORE)
            # Check if the request is a ping from the server
            if buffer != IGNORE:
                self.__trigger__(self.on_message_received, identifier=self.identifier,
                                 data=json.loads(buffer.decode("utf-8")))
            buffer = b''

        connection = self.socket
        connection_closed = False

        # Listening for multiple requests
        while not connection_closed and not self.ipc_client_closed:
            # Buffering one request
            buffer = b''
            while not connection_closed and not self.ipc_client_closed:
                try:
                    # Receive data
                    ready_to_read, _, _ = select.select([connection], [], [], 1)
                    if ready_to_read:
                        data = connection.recv(1024)
                        if data == IGNORE:
                            continue
                        # Check if the server closed the connection
                        if not data:
                            connection_closed = True
                            break

                        LOGGER.trace(
                            f"IPC Client  {self.identifier} : Received data from server: {data.decode('utf-8')}",
                            CORE)

                        # Buffering data
                        for byte in data:
                            if byte == int(EOT, 16):
                                flush_buffer()
                                break
                            else:
                                buffer += bytes([byte])

                    else:
                        try:
                            connection.send(IGNORE)
                        except socket.error:
                            connection_closed = True
                            break
                except OSError or socket.timeout:
                    connection_closed = True
                    break
                except Exception as e:
                    LOGGER.warning_exception(SocketClientListeningError(f"Socket Client '{self.identifier}'"
                                                                        f"encountered probably non critical "
                                                                        "issue while listening server"
                                                                        f"connection, look at"
                                                                        f"the initial"
                                                                        f"exception for more details.") + e, CORE)

            time.sleep(self.artificial_latency)  # Artificial latency for optimization purposes

        if connection_closed:
            LOGGER.info(f"Socket Client  '{self.identifier}' : Connection closed by the server.", CORE)
            connection.close()
            self.__trigger__(self.on_connection_closed, identifier=self.identifier, from_client=False)
        else:
            LOGGER.info(f"Socket Client  '{self.identifier}' : Connection closed by client.", CORE)
            connection.close()
            self.__trigger__(self.on_connection_closed, identifier=self.identifier, from_client=True)

    # Non blocking call, send given data to a specific connection
    def send_data(self, data: dict):
        """
        Sends data to the server.
        :param data: The data to send as a dict.

        :raises SocketClientSendError: If an error occurred while sending data to the server, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        connection = self.socket
        try:
            connection.sendall(json.dumps(data).encode("utf-8") + bytes([int(EOT, 16)]))
            LOGGER.trace(f"IPC Client {self.identifier} : Sent data to server: {data}", CORE)
            self.__trigger__(self.on_message_sent, identifier=self.identifier, data=data)
        except Exception as e:
            raise SocketClientSendError(f"Socket Client '{self.identifier}': "
                                        f"error while sending data to server, "
                                        f"look at the initial exception for more details."
                                        f"Data: {data}") + e

    # Close the server
    def close(self):
        """
        Closes the socket client.
        """
        self.ipc_client_closed = True
        try:
            self.socket.close()
        except Exception as e:
            raise SocketClientCloseError(f"Socket Client '{self.identifier}': "
                                         f"error while closing connection, look at the initial exception "
                                         f"for more details.") + e

        LOGGER.trace(f"IPC Client {self.identifier} : Client closed.", CORE)
        self.__trigger__(self.on_client_closed)

    # Trigger an event
    def __trigger__(self, callbacks: list, **kwargs):
        """
        Triggers an event.
        :param callback: The callback to trigger.
        :param kwargs: Kwargs to pass to the callback.
        """
        for callback in callbacks:
            try:
                callback(**kwargs)
            except Exception as e:
                LOGGER.warning_exception(SocketClientEventCallbackError(
                    f"Socket Client '{self.identifier}': error while triggering callback '{callback}' during an event, "
                    f"look at the initial exception for more details.") + e,
                                         CORE)

    # --- Shortcuts to register events ---
    def register_on_connection_accepted(self, callback):
        """
        Registers a callback for the on_connection_accepted event.
        :param callback: The callback to register.
        """
        self.on_connection_accepted.append(callback)

    def register_on_connection_refused(self, callback):
        """
        Registers a callback for the on_connection_refused event.
        :param callback: The callback to register.
        """
        self.on_connection_refused.append(callback)

    def register_on_connection_closed(self, callback):
        """
        Registers a callback for the on_connection_closed event.
        :param callback: The callback to register.
        """
        self.on_connection_closed.append(callback)

    def register_on_message_received(self, callback):
        """
        Registers a callback for the on_message_received event.
        :param callback: The callback to register.
        """
        self.on_message_received.append(callback)

    def register_on_message_sent(self, callback):
        """
        Registers a callback for the on_message_sent event.
        :param callback: The callback to register.
        """
        self.on_message_sent.append(callback)

    def register_on_client_closed(self, callback):
        """
        Registers a callback for the on_server_closed event.
        :param callback: The callback to register.
        """
        self.on_client_closed.append(callback)
