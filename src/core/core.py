"""
Core module of KuiX.
"""
import json
import multiprocessing
import os

from src.core.ipc.IpcServer import IpcServer
from src.core.process.KxProcess import __launch__ as launch
from src.core.Logger import LOGGER, CORE
from src.core.Exceptions import *


# TODO, with events, once the process is started and connected, register all existing strategies
# TODO, convert all GenericException raise to custom ones
# TODO, fix missing function arguments exceptions not being raised correctly
# TODO, add trace & info logs

class KuiX:

    @staticmethod
    def __setup_files__(path: str):
        try:
            if not path.endswith('/') and path != "":
                path += '/'
            os.makedirs(path + 'kuiX', exist_ok=True)
            os.makedirs(path + 'kuiX/Logs', exist_ok=True)
            os.makedirs(path + 'kuiX/Strategies', exist_ok=True)
            os.makedirs(path + 'kuiX/Components', exist_ok=True)
        except Exception as e:
            raise CoreSetupError("Error while setting up files for KuiX, "
                                 "look at the initial exception for more details.") + e
        return path + 'kuiX/'

    @staticmethod
    def Configured(func):

        def wrapper(self, *args, **kwargs):
            if self.configured:
                return func(self, *args, **kwargs)
            else:
                raise CoreNotConfigured(f"KuiX Core was not configured, please call 'configure' or "
                                        f"'load_json_config' method before calling method '{func.__name__}'.")

        return wrapper

    def __init__(self, path: str = ""):
        try:
            self.root_path = self.__setup_files__(path)
        except CoreSetupError as e:
            raise e.add_ctx("Error while instantiating KuiX Core")

        # --- PLACEHOLDERS ---
        # Core
        self.configured = False

        # Ipc
        self.ipc_server = None

        # Configuration
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
        except SocketServerBindError as e:
            raise e.add_ctx("Error while configuring KuiX Core")
        # Placeholder, register endpoints and events

    @Configured
    def startup(self):
        """
        Start KuiX.
        """
        # Register connection event
        self.ipc_server.register_on_connection_accepted(lambda identifier: self.kx_processes.append(identifier))
        # Accepts connection from processes
        self.ipc_server.accept_new_connections()

    def load_json_config(self, path: str = "config.json"):
        """
        Load KuiX configuration from a json file.
        :param path: Path to the json file.
        """
        try:
            with open(path) as f:
                config = json.load(f)
            self.configure(**config)
        except Exception as e:
            raise GenericException("Error while loading KuiX configuration from json, look at the initial exception "
                                   "for more details.") + e

    @staticmethod
    def generate_auth_key():
        """
        Generate a random auth key.
        """
        return os.urandom(256).hex()

    @staticmethod
    def generate_json_config(path: str = "config.json"):
        try:
            with open(path, "w") as f:
                json.dump({
                    "ipc_host": "localhost",
                    "ipc_port": 6969,
                    "auth_key": "",
                    "process_count": -1
                }, f, indent=1)
        except Exception as e:
            raise GenericException("Error while generating KuiX configuration, "
                                   "look at the initial exception for more details.") + e

    # --- PROCESS ---
    @Configured
    def create_process(self, identifier: str):
        """
        Create a new KX process.
        :param identifier: Identifier of the new process.
        """
        if identifier in self.kx_processes:
            raise ProcessAlreadyExists("Error while generating KuiX configuration")

        multiprocessing.Process(target=launch, args=(identifier, self.auth_key, self.ipc_host, self.ipc_port)).start()

    # --- STRATEGIES ---
    @Configured
    def register_strategy(self, name: str, import_path: str):
        """
        Register a strategy.
        :param name: Name of the strategy.
        :param import_path: Import path of the strategy.
        """
        if name in self.strategies:
            raise StrategyAlreadyRegistered(f"Strategy '{name}' already registered")
        self.strategies[name] = import_path
        # Push the strategy to all processes
        for process in self.kx_processes:
            try:
                response = self.ipc_server.send_blocking_request(process, "register_strategy",
                                                                 {"name": name, "import_path": import_path})
                if response["status"] == "error":
                    # deserialize exception
                    ex = deserialize(response["return"])
                    raise ex
            except SocketServerSendError or SocketServerCliIdentifierNotFound or KeyError or \
                   KxProcessStrategyImportError as e:
                LOGGER.warning_exception(e.add_ctx(f"Error from KuiX core while registering strategy '{name}'"), CORE)

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
            raise StrategyNotRegistered(f"Strategy {strategy_name} was not registered.")
        try:
            response = self.ipc_server.send_blocking_request(kx_process_identifier, "create_worker",
                                                             {"strategy_name": strategy_name,
                                                              "identifier": worker_identifier,
                                                              "config": config})
            if response["status"] == "error":
                ex = deserialize(response["return"])
                raise ex
        except (SocketServerSendError, SocketServerCliIdentifierNotFound, StrategyNotFoundError,
                WorkerAlreadyExistsError, GenericException) as e:
            raise e.add_ctx(f"Error from KuiX core while creating a new worker for strategy: '{strategy_name}'")

    @Configured
    def start_worker(self, kx_process_identifier, worker_identifier: str):
        """
        Start a worker.
        :param kx_process_identifier: Identifier of the KX process to use.
        :param worker_identifier: Identifier of the worker.
        """
        try:
            response = self.ipc_server.send_blocking_request(kx_process_identifier, "start_worker",
                                                             {"identifier": worker_identifier})
            if response["status"] == "error":
                ex = deserialize(response["return"])
                raise ex
        except (SocketServerSendError, SocketServerCliIdentifierNotFound, WorkerNotFoundError, GenericException) as e:
            raise e.add_ctx(f"Error from KuiX core while starting worker '{worker_identifier}' instanced on process "
                            f"'{kx_process_identifier}'")

    @Configured
    def stop_worker(self, kx_process_identifier, worker_identifier: str):
        """
        Stop a worker.
        :param kx_process_identifier: Identifier of the KX process to use.
        :param worker_identifier: Identifier of the worker.
        """
        try:
            response = self.ipc_server.send_blocking_request(kx_process_identifier, "stop_worker",
                                                             {"identifier": worker_identifier})
            if response["status"] == "error":
                ex = deserialize(response["return"])
                raise ex
        except (SocketServerSendError, SocketServerCliIdentifierNotFound, WorkerNotFoundError, GenericException) as e:
            raise e.add_ctx(f"Error from KuiX core while stopping worker '{worker_identifier}' instanced on process "
                            f"'{kx_process_identifier}'")

# TODO: Add register endpoint method