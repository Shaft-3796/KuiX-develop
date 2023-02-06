"""
Implementation of a secured socket for IPC using AES encryption and a simple key authentication.
"""
from Logger import LOGGER, INFO, WARNING, CORE
from src2.core.Security import Encryption
from src2.Utils import nonblocking, EOF
import socket
import json
import time


class SocketServer:
    """
    Implementation of a secured socket server used for IPC.
    AES encryption and a simple key authentication is used.
    """

    def __init__(self, host: str, port: str, encryption: Encryption, encrypt: bool = True,
                 artificial_latency: float = 0.1):
        # Args
        self.host = host
        self.port = port
        self.encryption = encryption
        self.encrypt = encrypt
        self.artificial_latency = artificial_latency

        # Socket
        self.connections = []
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen()

        # To close the socket
        self.closed = False

    @nonblocking("socket_connection_listener")
    def listen_for_connections(self, callback):
        """
        Accepts connections and executes a callback function.
        """
        while not self.closed:
            try:
                # Accept connection
                connection, address = self.socket.accept()
                # Authentication
                if self.encrypt:
                    authentication_payload = self.encryption.decrypt(connection.recv(1024))
                else:
                    authentication_payload = connection.recv(1024)
                authentication_payload = json.loads(authentication_payload.decode("utf-8"))
                # Check if the key is correct
                if authentication_payload["key"] == self.encryption.key:
                    self.connections.append(connection)
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
    def handle_connection(self, identifier, connection, request_callback, connection_closed_callback):
        """
        Listens for requests from the client.
        """

        def flush_buffer():
            nonlocal buffer
            if self.encrypt:
                buffer = self.encryption.decrypt(buffer)
            request_callback(identifier, connection, json.loads(buffer.decode("utf-8")))
            buffer = b''

        connection_closed = False
        retry = 0

        # Listening for multiple requests
        while not connection_closed and not self.closed:
            # Buffering one request
            buffer = b''
            while 1:
                try:
                    # Receive data
                    data = connection.recv(1024)
                    if not data:
                        connection_closed = True
                        break
                    for byte in data:
                        if byte == int(EOF, 16):
                            flush_buffer()
                        buffer += bytes([byte])
                    retry = 0  # Reset retry counter
                except Exception as e:
                    LOGGER.dump_exception(e, CORE, f"SocketServer: Exception while handling connection {identifier}.")
                    retry += 1
                    if retry > 5:
                        connection_closed = True
                        LOGGER.warning(f"SocketServer: Connection {identifier} closed, max retry exceeded.", CORE)

            time.sleep(self.artificial_latency)  # Artificial latency for optimization purposes

        if connection_closed:
            connection_closed_callback(identifier, connection)

    def close(self):
        """
        Closes the socket.
        """
        self.closed = True
        self.socket.close()
