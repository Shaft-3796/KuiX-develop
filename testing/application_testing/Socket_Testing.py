import threading
import time

from src.core.Logger import LOGGER
from src.core.networking.IPC_client import IPCClient
from src.core.networking.IPC_server import IPCServer

LOGGER.enable_verbose()

# --- Test IPC server ---

# Create a server
server = IPCServer("key")

# Start the server
server.accept_new_connections()

# --- Test IPC client ---

# Create a client
client = IPCClient("CLI1", "key")

# Connect to the server
client.connect()

#  --- MSG SENDING ---
server.send_data("CLI1", {"content": "Hello client!"})
client.send_data({"content": "Hello server!"})

# --- Closing ---
server.close()
client.close()
