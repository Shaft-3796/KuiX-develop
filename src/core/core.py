"""
Core module of KuiX.
"""
import json
import multiprocessing
import os

from src.core.ipc.IpcServer import IpcServer
from src.core.process.kxprocess import launch

# TODO, with events, once the process is started and connected, register all existing strategies

class KuiX:

    @staticmethod
    def __setup_files__(path: str):
        os.makedirs(path + 'kuiX', exist_ok=True)
        os.makedirs(path + 'kuiX/Logs', exist_ok=True)
        os.makedirs(path + 'kuiX/Strategies', exist_ok=True)
        os.makedirs(path + 'kuiX/Components', exist_ok=True)
        return path + 'kuiX/'

    @staticmethod
    def Configured(func):

        def wrapper(self, *args, **kwargs):
            if self.configured:
                return func(self, *args, **kwargs)
            else:
                raise Exception("KuiX not configured")

        return wrapper

    def __init__(self, path: str = None):
        self.root_path = self.__setup_files__(path)

        # --- PLACEHOLDERS ---
        # Core
        self.configured = False

        # Ipc
        self.ipc_server = None
        self.ipc_host = None
        self.ipc_port = None
        self.auth_key = None
        self.artificial_latency = None

        # Process
        self.process_count = None
        self.kx_processes = []  # type list[identifiers: str]

        # Strategies
        self.strategies = {}  # type dict[name: str, import_path: str]

    # --- CONFIGURATION ---
    def configure(self, ipc_host: str = "localhost", ipc_port: int = 6969, auth_key: str = "",
                  socket_artificial_latency: int = 0.1, process_count: int = -1):
        """
        Configure KuiX from python.
        :param ipc_host: Host used for the local inter process communication socket server.
        :param ipc_port: Port used for the local inter process communication socket server.
        :param auth_key: Authentication key used for the local inter process communication socket server, "" by default,
        this will automatically create an auth key.
        :param socket_artificial_latency: Artificial latency added to the local inter process communication socket
        server for optimization purposes.
        :param process_count: Number of processes to use. Set this number above available cpu count will lead to
        performance degradation. Set this number to -1 to automatically use all available cpu count.
        """
        self.ipc_host = ipc_host
        self.ipc_port = ipc_port
        self.auth_key = auth_key
        self.process_count = process_count
        self.configured = True

        # Instance IPC server
        try:
            self.ipc_server = IpcServer(self.auth_key, self.ipc_host, self.ipc_port, socket_artificial_latency)
        except Exception as e:
            raise Exception("Error while configuring KuiX") from e
        # Placeholder, register endpoints and events

    @Configured
    def startup(self):
        """
        Start KuiX.
        """
        try:
            self.ipc_server.accept_new_connections()
        except Exception as e:
            raise Exception("Error while starting KuiX") from e

    def load_json_config(self, path: str):
        """
        Load KuiX configuration from a json file.
        :param path: Path to the json file.
        """
        try:
            with open(path) as f:
                config = json.load(f)
            self.configure(**config)
        except Exception as e:
            raise Exception("Error while loading KuiX configuration") from e

    @staticmethod
    def generate_auth_key():
        """
        Generate a random auth key.
        """
        return os.urandom(256).hex()

    @staticmethod
    def generate_json_config(path: str):
        try:
            with open(path, "w") as f:
                json.dump({
                    "ipc_host": "localhost",
                    "ipc_port": 6969,
                    "auth_key": "",
                    "process_count": -1
                }, f)
        except Exception as e:
            raise Exception("Error while generating KuiX configuration") from e

    # --- PROCESS ---
    @Configured
    def create_process(self, identifier: str):
        """
        Create a new KX process.
        :param identifier: Identifier of the new process.
        """
        if identifier in self.kx_processes:
            raise Exception("Process already exists")

        multiprocessing.Process(target=launch, args=(identifier, self.ipc_host, self.ipc_port, self.auth_key)).start()
        # TODO: The process will be appended only with a connection event from the IPC server

    # --- STRATEGIES ---
    @Configured
    def _register_strategy(self, name: str, import_path: str):
        """
        Register a strategy.
        :param name: Name of the strategy.
        :param import_path: Import path of the strategy.
        """
        if name in self.strategies:
            raise Exception("Strategy already registered")
        self.strategies[name] = import_path
        # Push the strategy to all processes
        for process in self.kx_processes:
            self.ipc_server.send_fire_and_forget(process, "register_strategy", {"name": name, "import_path": import_path})

    @Configured
    def create_worker(self, kx_process_identifier, strategy_name: str, worker_identifier: str, config=None):
        """
        Create a new worker.
        :param kx_process_identifier: Identifier of the KX process to use.
        :param strategy_name: Name of the strategy to use.
        :param worker_identifier: Identifier of the worker.
        :param config: Arguments to pass to the strategy.
        """
        if config is None:
            config = {}
        if strategy_name not in self.strategies:
            raise Exception("Strategy not registered")
        self.ipc_server.send_fire_and_forget(kx_process_identifier, "create_worker", {"strategy_name": strategy_name,
                                                                                      "identifier": worker_identifier,
                                                                                      "config": config})

    @Configured
    def start_worker(self, kx_process_identifier, worker_identifier: str):
        """
        Start a worker.
        :param kx_process_identifier: Identifier of the KX process to use.
        :param worker_identifier: Identifier of the worker.
        """
        self.ipc_server.send_fire_and_forget(kx_process_identifier, "start_worker", {"identifier": worker_identifier})

    @Configured
    def stop_worker(self, kx_process_identifier, worker_identifier: str):
        """
        Stop a worker.
        :param kx_process_identifier: Identifier of the KX process to use.
        :param worker_identifier: Identifier of the worker.
        """
        self.ipc_server.send_fire_and_forget(kx_process_identifier, "stop_worker", {"identifier": worker_identifier})
