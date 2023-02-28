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


class SocketServer:
    """
    Implementation of a custom socket server used for IPC (Inter Process Communication).
    """

    # Constructor
    def __init__(self, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):
        """
        Instance a socket server used for inter process communication (IPC).
        :param auth_key: The key clients will use to authenticate themselves.
        :param port (optional): The port to listen on. Default is 6969.
        :param host (optional): The host to listen on. Default is localhost.
        :param artificial_latency (optional): Time in s between each .recv call for a connection. Default is 0.1s.
        This is used to prevent the CPU from being overloaded. Change this value if you know what you're doing.

        :raise SocketServerBindError: If the socket cannot be bound to the specified host and port.
        """
        # Args
        self.auth_key = auth_key
        self.host = host
        self.port = port
        self.artificial_latency = artificial_latency

        # Events
        self.on_connection_accepted = [lambda identifier: threading.Thread(target=self.listen_for_connection,
                                                                           args=(identifier,),
                                                                           name=identifier).start()]
        self.on_connection_refused = []
        self.on_connection_closed = []
        self.on_server_closed = []
        self.on_message_received = []
        self.on_message_sent = []

        # Socket
        self.connections = {}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(0.2)
        try:
            self.socket.bind((self.host, self.port))
        except Exception as e:
            raise SocketServerBindError(f"Socket Server failed to bind to {host}:{port}, "
                                        "look at the initial exception for more details.") + e
        self.socket.listen()

        # To close the IPC server
        self.ipc_server_closed = False
        # To stop accepting new connections, for optimization purposes
        self.accepting_new_connections = True

        LOGGER.trace(f"IPC Server: server fully instanced on {self.host}:{self.port}", CORE)

    # accept new connections from clients until self.accepting_new_connections is set to False
    @nonblocking("ipc_server_new_connection_listener")
    def accept_new_connections(self):
        """
        This method launches a new thread that will let the server accept new connections.
        """

        self.accepting_new_connections = True  # Assume we really want to accept new connections
        LOGGER.trace(f"IPC Server: Listening for incoming connections", CORE)
        while self.accepting_new_connections:
            try:
                # Accept connection
                connection, address = self.socket.accept()
                LOGGER.trace(f"IPC Server: Detected connection request from {address}", CORE)

                # Authentication
                authentication_payload = connection.recv(1024)  # We assume that the payload is less than 1024 bytes
                authentication_payload = json.loads(authentication_payload.decode("utf-8"))

                # Check if the key is correct
                if authentication_payload["key"] == self.auth_key:
                    # Validate a new connection
                    LOGGER.trace(f"IPC Server: Validated client creds for {address} "
                                 f"id: {authentication_payload['identifier']}", CORE)
                    connection.sendall(json.dumps({"status": "valid"}).encode("utf-8"))
                    self.connections[authentication_payload["identifier"]] = connection
                    self.__trigger__(self.on_connection_accepted, identifier=authentication_payload["identifier"])
                else:
                    # Invalid creds
                    LOGGER.trace(f"IPC Server: Invalid client creds for {address}", CORE)
                    connection.sendall(json.dumps({"status": "invalid"}).encode("utf-8"))
                    connection.close()
                    self.__trigger__(self.on_connection_refused, identifier=authentication_payload["identifier"])
            except socket.timeout or OSError:
                # Expected exception, just ignore it
                pass
            except OSError:
                if not self.accepting_new_connections:
                    LOGGER.trace(f"IPC Server: Stopped accepting new connections", CORE)
            except Exception as e:
                LOGGER.warning_exception(SocketServerAcceptError("Socket server encountered probably non critical "
                                                                 "issue while accepting new connections, "
                                                                 "look at the initial exception for more details.")
                                         + e, CORE)

                # Blocking call, handle requests from a specific connection

    def listen_for_connection(self, identifier: str):
        """
        Listens for a client connection and triggers the on_message_received event when a message is received.
        This method is blocking and called automatically when a new connection is accepted.
        :param identifier: The identifier of the connection (client) to listen for.
        """

        def flush_buffer():
            nonlocal buffer
            LOGGER.trace(f"IPC Server: Flushing buffer for connection {identifier}, buffer: {buffer}", CORE)
            if buffer != IGNORE:
                self.__trigger__(self.on_message_received, identifier=identifier,
                                 data=json.loads(buffer.decode("utf-8")))
            buffer = b''

        # Pre test
        if identifier not in self.connections:
            e = SocketServerClientNotFound(f"Socket server was asked to listen for connection of client "
                                           f"'{identifier}', but the client is not connected or the "
                                           f"identifier is wrong.")
            LOGGER.error_exception(e, CORE)
            return

        connection = self.connections[identifier]
        connection_closed = False

        # Listening for multiple requests
        while not connection_closed and not self.ipc_server_closed:
            # Buffering one request
            buffer = b''
            while not connection_closed and not self.ipc_server_closed:
                try:
                    # Receive data
                    ready_to_read, _, _ = select.select([connection], [], [], 1)
                    if ready_to_read:
                        data = connection.recv(1024)
                        if data == IGNORE:
                            continue
                        # Check if the client closed the connection
                        if not data:
                            connection_closed = True
                            break

                        LOGGER.trace(
                            f"IPC Server: Received data from connection {identifier}: {data.decode('utf-8')}",
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
                except socket.timeout or OSError:
                    connection_closed = True
                    break
                except Exception as e:
                    LOGGER.warning_exception(SocketServerListeningConnectionError(f"Socket Server encountered error "
                                                                                  f"while"
                                                                                  f"listening connection  of client "
                                                                                  f"'{identifier}', "
                                                                                  f"look at the initial exception for "
                                                                                  f"more details.") + e, CORE)

            time.sleep(self.artificial_latency)  # Artificial latency for optimization purposes

        if connection_closed:
            LOGGER.trace(f"Socket Server: Connection '{identifier}' closed by the client.", CORE)
            try:
                connection.close()
            except OSError:
                pass
            try:
                self.connections.pop(identifier)
            except KeyError:
                pass
            self.__trigger__(self.on_connection_closed, identifier=identifier, from_server=False)
        else:
            LOGGER.trace(f"Socket Server: Connection '{identifier}' closed by server.", CORE)
            try:
                connection.close()
            except OSError:
                pass
            try:
                self.connections.pop(identifier)
            except KeyError:
                pass
            self.__trigger__(self.on_connection_closed, identifier=identifier, from_server=True)

    # Non blocking call, send given data to a specific connection
    def send_data(self, identifier: str, data: dict):
        """
        Sends data to a connection (client).
        :param identifier: The identifier of the connection (client) to send data to.
        :param data: The data to send as a dict.

        :raises SocketServerClientNotFound: If the connection (client) is not found, if the client is not
        connected or the identifier is wrong.
        :raises SocketServerSendError: If an error occurred while sending data to the client, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """

        # Pre test
        if identifier not in self.connections:
            LOGGER.error(f"IPC Server: Connection {identifier} not found.", CORE)
            raise SocketServerClientNotFound(f"Socket server encountered error while sending data to a client.\n"
                                             f"Identifier: '{identifier}'.\n"
                                             f"The client is not connected or the identifier is wrong.")

        connection = self.connections[identifier]
        try:
            connection.sendall(json.dumps(data).encode("utf-8") + bytes([int(EOT, 16)]))
            LOGGER.trace(f"IPC Server: Sent data to connection {identifier}: {data}", CORE)
            self.__trigger__(self.on_message_sent, identifier=identifier, data=data)
        except Exception as e:
            raise SocketServerSendError(f"Socket Server encountered error while sending data to a client.\n"
                                        f"Identifier: '{identifier}'.\n"
                                        f"Data: {data}.\n"
                                        f"Look at the initial exception for more details.") + e

    # Close the server
    def close(self):
        """
        Closes the socket server.
        :raises SocketServerCloseError: If an error occurred while closing the server, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        self.accepting_new_connections = False
        self.ipc_server_closed = True
        try:
            self.socket.close()
        except Exception as e:
            raise SocketServerCloseError("Socket Server encountered error while closing the server.\n"
                                         "Look at the initial exception for more details.") + e
        LOGGER.trace(f"Socket Server: Server closed.", CORE)
        self.__trigger__(self.on_server_closed)

    # Trigger an event
    @staticmethod
    def __trigger__(callbacks: list, **kwargs):
        """
        Triggers an event.
        :param callback: The callback to trigger.
        :param kwargs: Kwargs to pass to the callback.
        """
        for callback in callbacks:
            try:
                callback(**kwargs)
            except Exception as e:
                LOGGER.warning_exception(SocketServerEventCallbackError(
                    f"Socket Server encountered error while calling callback '{callback.__name__}' during an event.\n"
                    f"Look at the initial exception for more details.") + e, CORE)

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

    def register_on_server_closed(self, callback):
        """
        Registers a callback for the on_server_closed event.
        :param callback: The callback to register.
        """
        self.on_server_closed.append(callback)
