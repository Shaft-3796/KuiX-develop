"""
This module implements a socket server used for IPC (Inter Process Communication).
"""
from src.core.Logger import LOGGER, INFO, WARNING, CORE
from src.core.Utils import nonblocking, EOF
import socket
import json
import time

class SocketClient:
    def __init__(self, identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):
        """
        SocketClient instantiation.
        :param identifier: The identifier of the client.
        :param auth_key: The key used to authenticate the client.
        :param port (optional): The port to connect to. Default is 6969.
        :param host (optional): The host to connect to. Default is localhost. We don't recommend changing this.
        :param artificial_latency (optional): Time in s between each .recv call for a connection. Default is 0.1s.
        """
        self.identifier = identifier
        self.auth_key = auth_key
        self.host = host
        self.port = port
        self.artificial_latency = artificial_latency

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self):
        try:
            self.socket.connect((self.host, self.port))
            authentication_payload = {"key": self.auth_key, "identifier": self.identifier}
            self.socket.sendall(json.dumps(authentication_payload).encode("utf-8"))
        except Exception as e:
            LOGGER.dump_exception(e, CORE, WARNING, "SocketClient: Failed to connect to server.")

    def send(self, data: dict):
        """
        Sends data to the server.
        :param data: The data to send.
        """
        try:
            self.socket.sendall(json.dumps(data).encode("utf-8") + bytes([int(EOF, 16)]))
        except Exception as e:
            LOGGER.dump_exception(e, CORE, f"SocketServer: Exception while sending data to server from "
                                           f"{self.identifier}.")

    @nonblocking()
    def handle_connection(self,
                          request_callback: callable = lambda *args: None,
                          connection_closed_callback: callable = lambda *args: None):
        """
        Starts the client listener.
        :param thread_identifier: The identifier of the thread, parameters added by the decorator.
        :param request_callback: The callback to execute when a request is received.
        :param connection_closed_callback: The callback to execute when the connection is closed.
        """

        def flush_buffer():
            nonlocal buffer
            request_callback(self.identifier, json.loads(buffer.decode("utf-8")))
            buffer = b''

        connection_closed = False
        retry = 0

        # Listening for multiple requests
        while not connection_closed:
            # Buffering one request
            buffer = b''
            while 1:
                try:
                    # Receive data
                    data = self.socket.recv(1024)
                    if not data:
                        connection_closed = True
                        break
                    for byte in data:
                        if byte == int(EOF, 16):
                            flush_buffer()
                        buffer += bytes([byte])
                    retry = 0  # Reset retry counter
                except Exception as e:
                    LOGGER.dump_exception(e, CORE, f"SocketServer: Exception while handling connection {self.identifier}.")
                    retry += 1
                    if retry > 5:
                        connection_closed = True
                        LOGGER.warning(f"SocketServer: Connection {self.identifier} closed, max retry exceeded.", CORE)

            time.sleep(self.artificial_latency)  # Artificial latency for optimization purposes

        if connection_closed:
            connection_closed_callback(self.identifier)

    def close(self):
        self.socket.close()
