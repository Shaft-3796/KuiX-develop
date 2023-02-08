import time

from src.core.networking.socket_server import SocketServer
from src.core.networking.socket_client import SocketClient
from src.core.Logger import LOGGER


# --- SOCKET SERVER --- #

def server_connection_callback(connection, address, identifier):
    print(f"[Server] New connection to the server from {address} with identifier {identifier}")
    server.handle_connection(identifier, server_request_callback, server_connection_closed_callback)


def server_request_callback(identifier, connection, request):
    print(f"[Server] New request from {identifier} with data {request}")


def server_connection_closed_callback(identifier, connection):
    print(f"[Server] Connection closed from {identifier}")


# Create a socket server
server = SocketServer("authkey")
server.listen_for_connections(server_connection_callback)

# --- SOCKET CLIENT --- #
def client_connection_callback():
    print(f"[Client] Connected to the server")
    client.handle_connection(client_request_callback, client_connection_closed_callback)

def client_request_callback(identifier, request):
    print(f"[Client] New request to {identifier} from server with data {request}")


def client_connection_closed_callback(identifier):
    print(f"[Client] Connection closed to {identifier} from server")


# Create a socket client
LOGGER.enable_verbose()
client = SocketClient("client 1", "authkey")
client.connect(client_connection_callback)
time.sleep(1)
client.send({"test": "test"})
time.sleep(1)
server.close()

# TODO resume: Lance ce module pour fixer l'erreur, rajouter un nouveau type de log, "TRACE"
#  qui dans le logger ne sera pas activé par defaut mais necessitera un call du type LOGGER.enable_verbose.
# Ce type de log sera utilisé par exemple dans le socket pour tout et n'importe quoi, les petites étapes et
# ce qui est très technique !

