"""
This module implements a socket server used for IPC (Inter Process Communication).
"""
from src.core.Logger import LOGGER, INFO, WARNING, CORE
from src.core.Utils import nonblocking, EOT
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
        self.closed = False

    def connect(self, connection_callback: callable = lambda *args: None):
        """
        Connects to the server.
        :param connection_callback: a callback to execute when the connection is established.
        :return:
        """
        try:
            self.socket.connect((self.host, self.port))
            LOGGER.trace(f"SocketClient {self.identifier}: Connected to the server.", CORE)
            connection_callback()
            authentication_payload = {"key": self.auth_key, "identifier": self.identifier}
            self.socket.sendall(json.dumps(authentication_payload).encode("utf-8"))
            LOGGER.trace(f"SocketClient {self.identifier}: Sent an auth request to the server", CORE)
        except Exception as e:
            LOGGER.dump_exception(e, CORE, WARNING, "SocketClient: Failed to connect to server.")

    def send(self, data: dict):
        """
        Sends data to the server.
        :param data: The data to send.
        """
        try:
            self.socket.sendall(json.dumps(data).encode("utf-8") + bytes([int(EOT, 16)]))
            LOGGER.trace(f"SocketClient {self.identifier}: Sent data to the server: {json.dumps(data)}", CORE)
        except Exception as e:
            LOGGER.dump_exception(e, CORE, f"SocketServer: Exception while sending data to server from "
                                           f"{self.identifier}.")

    @nonblocking("socket_client_connection_handler")
    def handle_connection(self,
                          request_callback: callable = lambda *args: None,
                          connection_closed_callback: callable = lambda *args: None):
        """
        Starts the client listener.
        :param thread_identifier: The identifier of the thread, parameters added by the decorator.
        :param request_callback: The callback to execute when a request is received.
        :param connection_closed_callback: The callback to execute when the connection is closed.
        """
        LOGGER.trace(f"SocketClient {self.identifier}: Handling connection.", CORE)

        def flush_buffer():
            nonlocal buffer
            LOGGER.trace(f"SocketClient {self.identifier}: Flushing buffer: {buffer}", CORE)
            request_callback(self.identifier, json.loads(buffer.decode("utf-8")))
            buffer = b''

        connection_closed = False
        retry = 0

        # Listening for multiple requests
        while not connection_closed and not self.closed:
            # Buffering one request
            buffer = b''
            while not connection_closed and not self.closed:
                try:
                    # Receive data
                    data = self.socket.recv(1024)
                    LOGGER.trace(f"SocketClient {self.identifier}: Received data from server: {data.decode('utf-8')}",
                                 CORE)
                    if not data:
                        connection_closed = True
                        break
                    for byte in data:
                        if byte == int(EOT, 16):
                            flush_buffer()
                        else:
                            buffer += bytes([byte])
                    retry = 0  # Reset retry counter
                except Exception as e:
                    LOGGER.dump_exception(e, CORE, f"SocketClient {self.identifier}: "
                                                   f"Exception while handling connection.")
                    retry += 1
                    if retry > 5:
                        connection_closed = True
                        LOGGER.warning(f"SocketClient {self.identifier}: Connection "
                                       f"closed, max retry exceeded.", CORE)

            time.sleep(self.artificial_latency)  # Artificial latency for optimization purposes

        print("CCCCCOOOOO CCCCLLLL")
        if connection_closed:
            LOGGER.trace(f"SocketClient {self.identifier}: Connection closed by the server", CORE)
            connection_closed_callback(self.identifier)
        else:
            LOGGER.trace(f"SocketClient {self.identifier}: Connection closed by the client", CORE)

    def close(self):
        """
        Closes the connection.
        :return:
        """
        LOGGER.trace(f"SocketClient {self.identifier}: Closing connection.", CORE)
        self.closed = True
        self.socket.close()


# TODO : Le serveur ou le client se close mais on dirait que les handlers restent bloqués à un certain point sans pour autant reloop.