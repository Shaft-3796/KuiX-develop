from src.core.networking.socket_server import SocketServer
from src.core.networking.socket_client import SocketClient


# --- SOCKET SERVER --- #

def server_connection_callback(connection, address, identifier):
    print(f"[Server] New connection to the server from {address} with identifier {identifier}")
    server.handle_connection(identifier, connection, server_request_callback, server_connection_closed_callback)


def server_request_callback(identifier, connection, request):
    print(f"[Server] New request from {identifier} with data {request}")


def server_connection_closed_callback(identifier, connection):
    print(f"[Server] Connection closed from {identifier}")


# Create a socket server
server = SocketServer("authkey")
server.listen_for_connections(server_connection_callback)

# --- SOCKET CLIENT --- #

def client_request_callback(identifier, request):
    print(f"[Client] New request to {identifier} from server with data {request}")


def client_connection_closed_callback(identifier):
    print(f"[Client] Connection closed to {identifier} from server")


# Create a socket client
client = SocketClient("client 1", "authkey")
client.connect()

# TODO resume: Lance ce module pour fixer l'erreur, rajouter un nouveau type de log, "TRACE"
#  qui dans le logger ne sera pas activé par defaut mais necessitera un call du type LOGGER.enable_verbose.
# Ce type de log sera utilisé par exemple dans le socket pour tout et n'importe quoi, les petites étapes et
# ce qui est très technique !

