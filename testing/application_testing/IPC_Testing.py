import threading
import time

from src.core.Logger import LOGGER
from src.core.ipc.IpcServer import IpcServer
from src.core.networking.SocketClient import SocketClient

LOGGER.enable_verbose()

# --- Test IPC server ---

# Create a server
server = IpcServer("key")

# Start the server
server.accept_new_connections()

# --- Test IPC client ---

# Create a client
client = SocketClient("CLI1", "key")

# Connect to the server
client.connect()

#  --- MSG SENDING ---
server.send_data("CLI1", {"content": "Hello client!"})
client.send_data({"content": "Hello server!"})

# --- Closing ---
server.close()
client.close()

# --- Test IPC server ---
print("Endpoints: ", server.endpoints)
