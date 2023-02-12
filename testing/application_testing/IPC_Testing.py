import threading
import time

from src.core.Logger import LOGGER
from src.core.ipc.IpcServer import IpcServer
from src.core.ipc.IpcClient import IpcClient

LOGGER.enable_verbose()

# --- Test IPC server ---

# Create a server
server = IpcServer("key")

# --- Test IPC client ---

# Create a client
client = IpcClient("CLI1", "key")


#  --- Blocking test ---
print("---- SENDING BLOCKING PING FROM CLIENT TO SERVER ----")
print(server.send_blocking_request("CLI1", "blocking_ping", {}))
print("Client Ping Sending Done")
print("-----------------------------------------------------")
