import inspect
import json
import socket
import threading
import time
from multiprocessing.managers import BaseManager
from src.core.Logger import dump_exception, log, LogTypes
from src.strategies.WorkerLoader import WorkerLoader

EOF = '04'


class ProcessInterface:

    def __init__(self, process_index, shared_memory, host: str, port: int, auth: str):
        self.process_index = process_index
        self.host = host
        self.port = port
        self.auth = auth

        self.shared_memory = shared_memory

        self.workers = {}

        self.api_endpoints = {}  # For API calls

        # Register API endpoints
        methods = inspect.getmembers(self, predicate=inspect.ismethod)
        for method in methods:
            method = method[1]
            if hasattr(method, "api_endpoint"):
                self.api_endpoints[method.api_endpoint] = method

        # Inter Process Communication (IPC) SOCKET
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))
        self.socket.sendall(auth.encode("utf-8"))

        # Inter Process Communication (IPC) SHARED MEMORY

    # --- IPC SOCKET ---
    def ipc_socket_listener(self):
        buffer = b''
        handler = 0
        while True:
            data = self.socket.recv(1024)
            for byte in data:
                if byte == int(EOF, 16):
                    threading.Thread(target=self.ipc_socket_handler,
                                     args=(buffer,),
                                     name=f"IPC_HANDLER_{handler}").start()
                    buffer = b''
                    handler += 1
                else:
                    buffer += bytes([byte])

    def ipc_socket_handler(self, data):
        data = json.loads(data.decode("utf-8"))
        if "args" not in data:
            data["args"] = []
        if "kwargs" not in data:
            data["kwargs"] = {}
        self.api_endpoints[data["endpoint"]](*data["args"], **data["kwargs"])

    def ipc_server_request(self, data):
        try:
            self.socket.sendall(json.dumps(data).encode("utf-8") + bytes.fromhex(EOF))
        except Exception as e:
            dump_exception(e, "[PROCESS] FAILED TO SEND IPC SERVER REQUEST")

    @staticmethod
    def api_endpoint(endpoint: str):
        def decorator(function):
            function.__setattr__("api_endpoint", endpoint)
            return function

        return decorator

    # --- IPC API ENDPOINTS --

    @api_endpoint("ping")
    def print_message(self, message: str):
        print(message)

    # Worker related
    @api_endpoint("create_worker")
    def create_worker(self, strategy_name, loader_key):
        loader = None
        try:
            loader = self.shared_memory.get_generic_object(loader_key)
            worker = self.shared_memory.get_strategy(strategy_name)(*loader.args, identifier=loader.identifier, **loader.kwargs)
            self.workers[loader.identifier] = worker
            self.shared_memory.add_worker_identifier(loader.identifier, self.process_index)
            log(LogTypes.INFO, f"[CORE] WORKER {loader.identifier} CREATED")
        except Exception as e:
            dump_exception(e, f"[PROCESS] ERROR WHILE CREATING WORKER {loader.identifier} of {strategy_name}")
            self.ipc_server_request({"endpoint": "create_worker_response", "kwargs": {"res": 1}})
        self.ipc_server_request({"endpoint": "create_worker_response", "kwargs": {"res": 0}})

    @api_endpoint("get_number_of_workers")
    def get_number_of_workers(self):
        return len(self.workers.keys())


def new_process(i, shared_memory, host, port, auth):
    process = ProcessInterface(i, shared_memory, host, port, auth)
    process.ipc_socket_listener()


"""
TODO:
Il faut fix la méthode ce création de worker dans Nestor.py pour bien répartir les workers dans les process
Réfléchir à rework les classes de stratégies pour que la fonction stratégie soit call en boucle par la classe,
de cette façon il revient à Nestor de vérifier si la stratégie doit être stoppée ou non.
"""
