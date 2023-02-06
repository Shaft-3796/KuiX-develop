import inspect
import json
import threading
from multiprocessing.managers import BaseManager
import multiprocessing
import os
import socket
import secrets

from .process.NestorProcessInterface import new_process, EOF
from .Logger import log, LogTypes, dump_exception
from src.strategies.BaseStrategy import BaseStrategy
from ..strategies.WorkerLoader import WorkerLoader


class Nestor:
    @staticmethod
    def __setup_files__(path: str):
        os.makedirs(path + 'Nestor', exist_ok=True)
        os.makedirs(path + 'Nestor/Logs', exist_ok=True)
        os.makedirs(path + 'Nestor/Strategies', exist_ok=True)
        os.makedirs(path + 'Nestor/Extensions', exist_ok=True)
        return path + 'Nestor/'

    def __init__(self, path: str = ""):
        # Check files setup
        self.root_path = Nestor.__setup_files__(path)

        # --- PLACEHOLDERS ---
        # Core
        self.configured = False

        # IPC
        self.processes = None
        self.process_count = None
        self.ipc_host = None
        self.ipc_port = None
        self.ipc_auth = None
        self.ipc_socket = None
        self.ipc_connections = None

        self.ipc_shared_memory_manager = None
        self.ipc_shared_memory = None

        self.api_endpoints = None

    # --- CONFIGURATION ---
    # Configure Nestor using python arguments
    def configure_from_python(self, ipc_port: int = 55550, process_count: int = 0):
        # Inter Process Communication (IPC) SHARED MEMORY
        class IPCSharedMemory:
            def __init__(self):
                self.strategies = {}
                self.worker_identifiers = {}
                self.generic_objects = {}

            def set_strategy(self, key, value):
                self.strategies[key] = value

            def get_strategy(self, key):
                return self.strategies[key]

            def is_strategy(self, name):
                return name in self.strategies.keys()

            def add_worker_identifier(self, identifier, process_index):
                self.worker_identifiers[
                    identifier] = process_index if identifier not in self.worker_identifiers else None

            def remove_worker_identifier(self, identifier):
                try:
                    self.worker_identifiers.pop(identifier)
                except ValueError:
                    pass

            def get_worker_identifier(self, identifier):
                try:
                    return self.worker_identifiers[identifier]
                except ValueError:
                    pass

            def is_worker_identifier(self, identifier):
                return identifier in self.worker_identifiers.keys()

            def get_generic_object(self, key):
                try:
                    return self.generic_objects[key]
                except ValueError:
                    pass

            def set_generic_object(self, key, value):
                self.generic_objects[key] = value

            def add_generic_object(self, value):
                key = secrets.token_hex(16)
                self.generic_objects[key] = value
                return key

            def is_generic_object(self, key):
                return key in self.generic_objects.keys()

            def remove_generic_object(self, key):
                try:
                    self.generic_objects.pop(key)
                except ValueError:
                    pass

        try:
            self.ipc_shared_memory_manager = BaseManager()
            self.ipc_shared_memory_manager.register("IPCSharedMemory", IPCSharedMemory)
            self.ipc_shared_memory_manager.start()
            self.ipc_shared_memory = self.ipc_shared_memory_manager.IPCSharedMemory()
        except Exception as e:
            dump_exception(e, "[CORE] IPC SHARED MEMORY ERROR")
            exit(1)
        log(LogTypes.INFO, "[CORE] IPC SHARED MEMORY SETUP COMPLETE")

        # Inter Process Communication (IPC) SOCKET
        self.process_count = process_count if process_count > 0 else multiprocessing.cpu_count()
        self.ipc_host = socket.gethostname()
        self.ipc_port = ipc_port
        self.ipc_auth = secrets.token_hex(32)
        self.ipc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.processes = {}
        self.ipc_connections = {}
        try:
            self.ipc_socket.bind((self.ipc_host, self.ipc_port))
            self.ipc_socket.listen(1)
            for i in range(self.process_count):
                process = multiprocessing.Process(target=new_process,
                                                  args=(i, self.ipc_shared_memory, self.ipc_host, self.ipc_port,
                                                        self.ipc_auth),
                                                  name=f"PROCESS_{i}")
                process.start()
                ipc_connection, addr = self.ipc_socket.accept()
                auth = ipc_connection.recv(1024).decode("utf-8")
                if auth == self.ipc_auth:
                    self.processes[i] = process
                    self.ipc_connections[i] = ipc_connection
        except Exception as e:
            dump_exception(e, "[CORE] IPC SOCKET SERVER CONNECTION ERROR")
            exit(1)
        log(LogTypes.INFO, "[CORE] IPC SOCKET SETUP COMPLETE")
        # Register API endpoints
        self.api_endpoints = {}
        methods = inspect.getmembers(self, predicate=inspect.ismethod)
        for method in methods:
            method = method[1]
            if hasattr(method, "api_endpoint"):
                self.api_endpoints[method.api_endpoint] = method

        threading.Thread(target=self.__ipc_socket_listener__, name="CORE_IPC_SOCKET_LISTENER").start()

        self.configured = True

    # Generate a configuration file with default values
    def generate_config_file(self):
        with open(self.root_path + "core_config.json", "w") as file:
            json.dump({"ipc_port": 55550, "process_count": 0}, file, indent=4)

    # Configure Nestor using a config file
    def configure_from_file(self):
        try:
            with open(self.root_path + 'core_config.json', "r") as file:
                config = json.load(file)
            self.configure_from_python(**config)
        except Exception as e:
            dump_exception(e, "[CORE] CONFIGURATION FROM FILE ERROR, file corrupted or removed, regenerate one using "
                              "Nestor.generate_config_file()")
            exit(1)

    # --- MISC ---
    # Check if Nestor is configured before using a method
    @staticmethod
    def configured_only(function):
        def wrapper(*args, **kwargs):
            if args[0].configured:
                return function(*args, **kwargs)
            else:
                log(LogTypes.ERROR, f"[CORE] {function.__name__}() called before Nestor.configure_from_python() or "
                                    f"Nestor.configure_from_file(), please configure Nestor before using it.")
                exit(1)

        return wrapper

    # --- IPC SOCKET ---
    # Listen for incoming IPC requests
    def __ipc_socket_listener__(self):
        # We would be able to run a thread to listen incoming requests for each process
        # but because we prefer to have some latency instead of performance drops for strategies
        # we listen requests from all processes in the same thread
        buffer = [b'' for _ in range(len(self.ipc_connections))]
        handler = 0
        log(LogTypes.INFO, "[CORE] IPC SOCKET LISTENER STARTED")
        while True:
            try:
                for i in range(len(self.ipc_connections)):
                    connection = self.ipc_connections[i]
                    data = connection.recv(1024)
                    for byte in data:
                        if byte == int(EOF, 16):
                            threading.Thread(target=self.ipc_socket_handler,
                                             args=(buffer[i], ),
                                             name=f"IPC_SERVER_HANDLER_{i, handler}").start()
                            buffer[i] = b''
                            handler += 1
                        else:
                            buffer[i] += bytes([byte])
            except Exception as e:
                dump_exception(e, "[CORE] IPC SOCKET LISTENER ERROR")
                exit(1)

    def ipc_process_request(self, process_index, data):
        try:
            self.ipc_connections[process_index].sendall(json.dumps(data).encode("utf-8") + bytes.fromhex(EOF))
        except Exception as e:
            dump_exception(e, "[CORE] FAILED TO SEND IPC SERVER REQUEST")

    @configured_only
    def ipc_socket_handler(self, data):
        try:
            data = json.loads(data.decode("utf-8"))
            self.api_endpoints[data["endpoint"]](**data["kwargs"])
        except Exception as e:
            log(LogTypes.WARNING, f"[CORE] Unknow endpoint or malformed data:\n{data}")

    # --- IPC API ENDPOINTS ---
    @staticmethod
    def api_endpoint(endpoint: str):
        def decorator(function):
            function.__setattr__("api_endpoint", endpoint)
            return function

        return decorator

    # --- CORE ---


    # --- STRATEGIES & WORKER ---
    def add_strategy(self, strategy):
        self.ipc_shared_memory.set_strategy(strategy.NAME, strategy)
        log(LogTypes.INFO, f"[CORE] STRATEGY {strategy.NAME} ADDED")

    def create_worker(self, strategy_name: str, loader: WorkerLoader):
        try:
            # Fetch for existing worker
            if self.ipc_shared_memory.is_worker_identifier(loader.identifier):
                log(LogTypes.WARNING, f"[CORE] WORKER {loader.identifier} ALREADY EXISTS, IGNORING.")
                return 'WORKER_EXISTS'
            if not self.ipc_shared_memory.is_strategy(strategy_name):
                log(LogTypes.WARNING, f"[CORE] UNKNOWN STRATEGY {strategy_name} REGISTER IT BEFORE CREATING A WORKER.")
                return 'UNKNOWN_STRATEGY'
            else:
                # Add loader to shared memory
                key = self.ipc_shared_memory.add_generic_object(loader)
                # Create new worker
                self.ipc_process_request(self.ipc_shared_memory.get_worker_identifier(loader.identifier),
                                         {"endpoint": "create_worker", "args": [strategy_name, key]})
                return 'WORKER_CREATEATION_SUBMITTED'
        except Exception as e:
            dump_exception(e, f"[CORE] WORKER CREATION ERROR, most likely due to shared memory corruption")
            return 'WORKER_CREATION_ERROR'
