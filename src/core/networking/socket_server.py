"""
This module implements a socket server used for IPC (Inter Process Communication).
"""
from src.core.Logger import LOGGER, INFO, WARNING, TRACE, CORE
from src.core.Utils import nonblocking, EOT
import socket
import json
import time


class SocketServer:
    """
    Implementation of a socket server used for IPC (Inter Process Communication).
    """

    def __init__(self, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):
        """
        SocketServer instantiation.
        :param auth_key: The key used to authenticate clients.
        :param port (optional): The port to listen on. Default is 6969.
        :param host (optional): The host to listen on. Default is localhost. We don't recommend changing this.
        :param artificial_latency (optional): Time in s between each .recv call for a connection. Default is 0.1s.
        This is used to prevent the CPU from being overloaded.
        """
        # Args
        self.auth_key = auth_key
        self.host = host
        self.port = port
        self.artificial_latency = artificial_latency

        # Socket
        self.connections = {}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen()
        LOGGER.trace(f"SocketServer: Listening on {self.host}:{self.port}", CORE)

        # To close the socket
        self.closed = False

    @nonblocking("socket_connection_listener")
    def listen_for_connections(self, callback: callable = lambda *args: None):
        """
        Starts the new connection listener.
        """
        LOGGER.trace(f"SocketServer: Listening for incoming connections", CORE)
        while not self.closed:
            try:
                # Accept connection
                connection, address = self.socket.accept()
                LOGGER.trace(f"SocketServer: Accepted connection from {address}", CORE)
                # Authentication
                authentication_payload = connection.recv(1024)
                authentication_payload = json.loads(authentication_payload.decode("utf-8"))
                # Check if the key is correct
                if authentication_payload["key"] == self.auth_key:
                    LOGGER.trace(f"SocketServer: Validated client creds for {address} id: "
                                 f"{authentication_payload['identifier']}", CORE)
                    self.connections[authentication_payload["identifier"]] = connection
                    # Execute callback
                    callback(connection, address, authentication_payload["identifier"])
                else:
                    LOGGER.warning(f"SocketServer: Invalid key received from client. "
                                   f"Received {authentication_payload['key']} for "
                                   f"{authentication_payload['identifier']} client", CORE)

                time.sleep(0.1)  # Artificial latency for optimization purposes
            except Exception as e:
                LOGGER.dump_exception(e, CORE, "SocketServer: Exception while listening for connections.")

    @nonblocking("socket_connection_handler")
    def handle_connection(self, identifier,
                          request_callback: callable = lambda *args: None,
                          connection_closed_callback: callable = lambda *args: None):
        """
        Starts the client listener.
        :param identifier: The identifier of the client.
        :param request_callback: The callback to execute when a request is received.
        :param connection_closed_callback: The callback to execute when the connection is closed.
        """
        LOGGER.trace(f"SocketServer: Handling connection {identifier}", CORE)

        def flush_buffer():
            nonlocal buffer
            LOGGER.trace(f"SocketServer: Flushing buffer for connection {identifier}, buffer: {buffer}", CORE)
            request_callback(identifier, connection, json.loads(buffer.decode("utf-8")))
            buffer = b''

        def close_connection():
            nonlocal connection_closed
            connection_closed = True

        if identifier not in self.connections:
            LOGGER.error(f"SocketServer: Connection {identifier} not found.", CORE)
            return
        connection = self.connections[identifier]
        connection_closed = False
        retry = 0

        # Listening for multiple requests
        while not connection_closed and not self.closed:
            # Buffering one request
            buffer = b''
            while not connection_closed and not self.closed:
                try:
                    # Receive data
                    data = connection.recv(1024)
                    LOGGER.trace(f"SocketServer: Received data from connection {identifier}: {data.decode('utf-8')}",
                                 CORE)
                    if not data:
                        close_connection()
                        break
                    for byte in data:
                        if byte == int(EOT, 16):
                            flush_buffer()
                            break
                        else:
                            buffer += bytes([byte])
                    retry = 0  # Reset retry counter
                except Exception as e:
                    LOGGER.dump_exception(e, CORE, f"SocketServer: Exception while handling connection {identifier}.")
                    retry += 1
                    if retry > 5:
                        close_connection()
                        LOGGER.warning(f"SocketServer: Connection {identifier} closed, max retry exceeded.", CORE)
                print("RELOOPING 1")
            print("RELOOPING 2")
            time.sleep(self.artificial_latency)  # Artificial latency for optimization purposes
            print("RELOOPING 3")

        if connection_closed:
            LOGGER.trace(f"SocketServer: Connection {identifier} closed.", CORE)
            connection_closed_callback(identifier, connection)
        else:
            LOGGER.trace(f"SocketServer: Connection {identifier} closed by server.", CORE)

    def send(self, identifier, data: dict):
        """
        Sends data to a client.
        :param identifier: The identifier of the client.
        :param data: The data to send.
        """
        if identifier not in self.connections:
            LOGGER.error(f"SocketServer: Connection {identifier} not found.", CORE)
            return
        connection = self.connections[identifier]
        try:
            connection.sendall(json.dumps(data).encode("utf-8") + bytes([int(EOT, 16)]))
            LOGGER.trace(f"SocketServer: Sent data to connection {identifier}: {data}", CORE)
        except Exception as e:
            LOGGER.dump_exception(e, CORE, f"SocketServer: Exception while sending data to connection {identifier}.")

    def close(self):
        """
        Closes the socket.
        """
        LOGGER.trace(f"SocketServer: Closing socket.", CORE)
        self.closed = True
        self.socket.close()
