"""
This module implements an IPC custom protocol using sockets.
"""
import select
import threading
from typing import Callable

from src.core.Exceptions import *
from src.core.Logger import LOGGER, INFO, WARNING, TRACE, CORE
from src.core.Utils import nonblocking, EOT, IGNORE
import socket
import json
import time


class SocketClient:
    """
    Implementation of a custom socket server used for IPC (Inter Process Communication).

    Methods:
        __init__(identifier, auth_key, host, port, artificial_latency)
        Instance the server socket, do not raise any exception.

        connect()

    """

    # Constructor
    def __init__(self, _identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):
        """
        IPC server instantiation.
        :param _identifier: The identifier of the server.
        :param auth_key: The key used to authenticate clients.
        :param port (optional): The port to listen on. Default is 6969.
        :param host (optional): The host to listen on. Default is localhost. We don't recommend changing this.
        :param artificial_latency (optional): Time in s between each .recv call for a connection. Default is 0.1s.
        This is used to prevent the CPU from being overloaded.
        """
        # Args
        self.identifier = _identifier
        self.auth_key = auth_key
        self.host = host
        self.port = port
        self.artificial_latency = artificial_latency

        # Events
        self.on_connection_accepted = [lambda identifier: threading.Thread(target=self.listen_for_connection,
                                                                           name=identifier).start()]
        self.on_connection_refused = []
        self.on_connection_closed = []
        self.on_client_closed = []
        self.on_message_received = []
        self.on_message_sent = []

        # Socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # To close the IPC client
        self.ipc_client_closed = False

        LOGGER.trace(f"IPC Client {self.identifier} : client fully instanced and ready to connect on "
                     f"{self.host}:{self.port}", CORE)

    # --- Low level methods ---

    # Connect to the server
    def connect(self):
        """
        Connects to the server.
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
        except BaseException as e:
            raise SocketClientConnectionError(e).add_note(f"Socket Client '{self.identifier}' failed to connect "
                                                          f"to {self.host}:{self.port}")

    # Blocking call, handle requests from the server
    def listen_for_connection(self):
        """
        Listens for the connection.
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
        retry = 0

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

                        retry = 0  # Reset retry counter
                    else:
                        try:
                            connection.send(IGNORE)
                        except socket.error:
                            connection_closed = True
                            break
                except OSError or socket.timeout:
                    connection_closed = True
                    break
                except BaseException as e:
                    LOGGER.dump_exception(e, CORE, f"IPC Client  {self.identifier} : "
                                                   f"Exception while handling connection.")
                    LOGGER.warning_exception(SocketClientListeningError(e)
                                             .add_note(f"Socket Client '{self.identifier}'"
                                                       f": error while listening connection."), CORE)
                    retry += 1
                    if retry > 5:
                        connection_closed = True
                        LOGGER.warning(f"Socket Client '{self.identifier}': "
                                       f"max retry exceeded, closing connection.", CORE)
                        break

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
        Sends data to a connection with a specific identifier.
        :param data: The data to send.
        """
        connection = self.socket
        try:
            connection.sendall(json.dumps(data).encode("utf-8") + bytes([int(EOT, 16)]))
            LOGGER.trace(f"IPC Client {self.identifier} : Sent data to server: {data}", CORE)
            self.__trigger__(self.on_message_sent, identifier=self.identifier, data=data)
        except BaseException as e:
            raise SocketClientSendError(e).add_note(f"Socket Client '{self.identifier}': "
                                                    f"error while sending data to server. "
                                                    f"Data: {data}")

    # Close the server
    def close(self):
        """
        Closes the server.
        """
        self.ipc_client_closed = True
        try:
            self.socket.close()
        except BaseException as e:
            raise SocketClientCloseError(e).add_note(f"Socket Client '{self.identifier}': "
                                                     f"error while closing connection.")

        LOGGER.trace(f"IPC Client {self.identifier} : Client closed.", CORE)
        self.__trigger__(self.on_client_closed)

    # Trigger an event
    def __trigger__(self, callbacks: list, **kwargs):
        """
        Triggers an event.
        :param callback: The callback to trigger.
        :param args: The args to pass to the callback.
        :param kwargs: The kwargs to pass to the callback.
        """
        for callback in callbacks:
            try:
                callback(**kwargs)
            except Exception as e:
                LOGGER.warning_exception(SocketClientEventCallbackError(e).add_note(
                    f"Socket Client '{self.identifier}': error while triggering callback '{callback}' during an event"),
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
