"""
Core module of KuiX.
"""
import json
import multiprocessing
import os
import time

from src.core.ipc.IpcServer import IpcServer
from src.core.process.KxProcess import __launch__ as launch
from src.core.Logger import LOGGER, CORE
from src.core.Exceptions import *


# TODO, with events, once the process is started and connected, register all existing strategies
# TODO, with events, once the process is started and connected, register all existing process components
# TODO, add trace & info logs
# TODO, automatically register built-in strategies
# TODO, automatically register built-in process components

class KuiX:

    @staticmethod
    def __setup_files__(path: str):
        """
        Setup filesystem for KuiX.
        :param path: Root path of KuiX.
        :return: the root path of KuiX folders.

        :raises CoreSetupError: if an error occurred while setting up KuiX files, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
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
    def configured(func):

        def wrapper(self, *args, **kwargs):
            if self.configured:
                return func(self, *args, **kwargs)
            else:
                raise CoreNotConfigured(f"KuiX Core was not configured, please call 'configure' or "
                                        f"'load_json_config' method before calling method '{func.__name__}'.")

        return wrapper

    def __init__(self, path: str = ""):
        """
        Instance a KuiX Core, this method will set up the filesystem for KuiX and create placeholders.
        :param path: root path of KuiX, if not specified, the current working directory will be used.

        :raises CoreSetupError: if an error occurred while setting up KuiX files, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
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
        self.process_components = {}  # type dict[name: str, import_path: str]

        # Strategies
        self.strategies = {}  # type dict[name: str, [import_path: str, config: dict]]

    # --- CONFIGURATION ---
    def configure(self, ipc_host: str = "localhost", ipc_port: int = 6969, auth_key: str = "",
                  socket_artificial_latency: int = 0.1, process_count: int = -1):
        """
        Configure KuiX core directly from a python function call.
        :param ipc_host: Host used for the local inter process communication socket server.
        :param ipc_port: Port used for the local inter process communication socket server.
        :param auth_key: Authentication key used for the local inter process communication socket server to
        authenticate clients, "" by default,
        this will automatically create an auth key.
        :param socket_artificial_latency: Artificial latency added to the local inter process communication socket
        server for optimization purposes.
        :param process_count: Number of processes to use. Set this number above available cpu count will lead to
        performance degradation. Set this number to -1 to automatically use all available cpu count.

        :raises SocketServerBindError: if an error occurred while binding the local inter process communication
        socket server.
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

    def load_json_config(self, path: str = "config.json"):
        """
        Load KuiX configuration from a json file.
        :param path: Path to the json file.

        :raises SocketServerBindError: if an error occurred while binding the local inter process communication
        socket server.
        :raises CoreConfigLoadError: if an error occurred while loading KuiX configuration from json, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        """
        try:
            with open(path) as f:
                config = json.load(f)
            self.configure(**config)
        except SocketServerBindError as e:
            raise e.add_ctx("Error while loading KuiX configuration from json")
        except Exception as e:
            raise CoreConfigLoadError(
                "Error while loading KuiX configuration from json, look at the initial exception "
                "for more details.") + e

    @configured
    def start(self):
        """
        Start KuiX. (non blocking)
        """
        # Register connection event
        self.ipc_server.register_on_connection_accepted(lambda identifier: self.kx_processes.append(identifier))
        # Accepts connection from processes
        self.ipc_server.accept_new_connections()

    @staticmethod
    def generate_auth_key():
        """
        Generate a random 256b auth key.
        """
        return os.urandom(256).hex()

    @staticmethod
    def generate_json_config(path: str = "config.json"):
        """
        Generate a json configuration with default values.
        :param path: path to the json file.

        :raises CoreConfigGenerationError: if an error occurred while generating KuiX configuration, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        """
        try:
            with open(path, "w") as f:
                json.dump({
                    "ipc_host": "localhost",
                    "ipc_port": 6969,
                    "auth_key": "",
                    "process_count": -1
                }, f, indent=1)
        except Exception as e:
            raise CoreConfigGenerationError("Error while generating KuiX configuration, "
                                            "look at the initial exception for more details.") + e

    # --- ENDPOINTS ---
    @configured
    def register_endpoint(self, name: str, callback: callable):
        """
        Register an endpoint, a method accessible from sub processes through IPC.
        :param name: Name of the endpoint.
        :param callback: Callback function to call when the endpoint is called.
        """
        if name in self.ipc_server.endpoints:
            LOGGER.warning(f"Core register_endpoint: endpoint '{name}' already exists, "
                           f"the first endpoint will be overwritten but this is probably an unexpected behavior.", CORE)
        self.ipc_server.endpoints[name] = callback

    @configured
    def register_blocking_endpoint(self, name: str, callback: callable):
        """
        Register a blocking endpoint, a method accessible from sub processes through the IPC.
        This endpoint is blocking, the core will wait for the endpoint to send a response the
        'self.send_response' method.
        WARNING: This is a blocking method, it will block the sub processes until the endpoint returns a value, if your
        method does not send a response using the 'self.send_response' method, some methods will block forever !
        :param name: Name of the endpoint.
        :param callback: Callback function to call when the endpoint is called. This function must absolutely
        call only one time the 'self.send_response' method.
        """
        if name in self.ipc_server.endpoints:
            LOGGER.warning(f"Core register_blocking_endpoint: endpoint '{name}' already exists, "
                           f"the first endpoint will be overwritten but this is probably an unexpected behavior.", CORE)
        self.ipc_server.blocking_endpoints[name] = callback

    # --- IPC ---
    def send(self, process_identifier, endpoint: str, data: dict):
        """
        Send data as a dict to a process through the IPC.
        :param process_identifier: Identifier of the process to send the data to.
        :param endpoint: Name of the endpoint to call on the process as registered with the 'register_endpoint'
        method of the client.
        :param data: Data to send as a dict

        :raises SocketServerSendError: if an error occurred while sending the data to the process, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        """
        try:
            self.ipc_server.send_fire_and_forget_request(endpoint, data)
        except SocketServerSendError as e:
            raise e.add_ctx(f"Core _ipc_send: error while sending data to "
                            f"endpoint '{endpoint}' to process '{process_identifier}'.")

    def send_and_block(self, process_identifier, endpoint: str, data: dict):
        """
        Send data as a dict to a process through the IPC and wait for the response.
        :param process_identifier: Identifier of the process to send the data to.
        :param endpoint: Name of the endpoint to call on the process as registered with the 'register_endpoint'
        method of the client.
        :param data: Data to send as a dict

        :raises SocketServerSendError: if an error occurred while sending the data to the process, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        """
        try:
            return self.ipc_server.send_blocking_request(endpoint, data)
        except SocketServerSendError as e:
            raise e.add_ctx(f"Core _ipc_send: error while sending data to blocking "
                            f"endpoint '{endpoint}' to process '{process_identifier}'.")

    def send_response(self, process_identifier, endpoint: str, data: dict, rid: str):
        """
        Send the response of a blocking request.
        :param process_identifier: Identifier of the process to send the data to.
        :param endpoint: Name of the endpoint to call on the process as registered with the 'register_endpoint'
        :param data: Data to send as a dict
        :param rid: Request id of the request to respond to.

        :raises SocketServerSendError: if an error occurred while sending the data to the process, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        """
        try:
            self.ipc_server.send_response(endpoint, data, rid)
        except SocketServerSendError as e:
            raise e.add_ctx(f"Core ipc_send_response: error while sending response to blocking "
                            f"endpoint '{endpoint}' to process '{process_identifier}'.")

    # --- PROCESS ---
    @configured
    def create_process(self, identifier: str):
        """
        Launch a new KxProcess running in a separate process. (non-blocking)
        :param identifier: Identifier of the new process.

        :raises ProcessAlreadyExists: if a process with the same identifier already exists.
        """
        if identifier in self.kx_processes:
            raise ProcessAlreadyExists("Error while creating a process, a process with the same identifier already "
                                       "exists")

        multiprocessing.Process(target=launch, args=(identifier, self.auth_key, self.ipc_host, self.ipc_port)).start()

    @configured
    def create_process_and_wait(self, identifier: str):
        """
        Launch a new KxProcess running in a separate process. (blocking)
        :param identifier: Identifier of the new process.

        :raises ProcessAlreadyExists: if a process with the same identifier already exists.
        """
        self.create_process(identifier)
        acc = 0
        while identifier not in self.kx_processes and acc < 30:
            time.sleep(0.1)
            acc += 0.1
        if identifier not in self.kx_processes:
            raise ProcessLaunchError("Error while creating a process, the process timed out. Check the logs.")

    @configured
    def close_process(self, kx_process_identifier: str):
        """
        Close a KxProcess.
        :param kx_process_identifier: Identifier of the process to close.

        :raises ProcessNotFound: if the KxProcess was not found.
        :raises SocketServerSendError: if an error occurred while sending the data to the process, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        :raises SocketServerClientNotFound: if the client was not found.
        :raises GenericException: if an error occurred while closing the process.
        """
        if kx_process_identifier not in self.kx_processes:
            raise ProcessNotFound(f"KxProcess '{kx_process_identifier}' not found.")
        try:
            response = self.ipc_server.send_blocking_request(kx_process_identifier, "close_process", {})
            if response["status"] == "error":
                ex = deserialize(response["return"])
                raise ex
        except (SocketServerSendError, SocketServerClientNotFound, GenericException) as e:
            raise e.add_ctx(f"Error from KuiX core while closing process '{kx_process_identifier}'")

    # --- STRATEGIES ---
    @configured
    def register_strategy(self, name: str, import_path: str):
        """
        Register a strategy to be used by all KxProcesses.
        :param name: Name of the strategy, this have to be the name of the class to import.
        :param import_path: Absolute path of the module file where the strategy is located.

        :raises StrategyAlreadyRegistered: if a strategy with the same name already exists.
        :raises SocketServerSendError: if an error occurred while sending the data to the process, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        :raises SocketServerClientNotFound: if the client was not found.
        :raises KxProcessStrategyImportError: if an error occurred while importing the strategy on the KxProcess.
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
            except (SocketServerSendError, SocketServerClientNotFound, KeyError,
                    KxProcessStrategyImportError) as e:
                LOGGER.error_exception(e.add_ctx(f"Error from KuiX core while registering strategy '{name}'"), CORE)

    @configured
    def create_worker(self, kx_process_identifier, strategy_name: str, worker_identifier: str, config=None):
        """
        Instance a new worker from a strategy class. When instancing a worker, you have to choose a KxProcess to
        use. The worker will be created in the KxProcess and will not be accessible directly from the KuiX core or
        another process.
        :param kx_process_identifier: Identifier of the KX process to use.
        :param strategy_name: Name of the strategy to use.
        :param worker_identifier: Identifier of the worker.
        :param config: Arguments to pass to the strategy '__init__' method.

        :raises ProcessNotFound: if the KxProcess was not found.
        :raises StrategyNotRegistered: if the strategy was not registered.
        :raises SocketServerSendError: if an error occurred while sending the request to the KxProcess.
        :raises SocketServerClientNotFound: if the KxProcess was not found.
        :raises StrategyNotFoundError: if the strategy was not found in the KxProcess.
        :raises WorkerAlreadyExistsError: if a worker with the same identifier already exists in the KxProcess.
        :raises GenericException: if an error occurred while creating the worker in the KxProcess.
        To get more details as a developer, look at the 'initial_type' and 'initial_msg' attributes of the
        raised exception.
        """
        if kx_process_identifier not in self.kx_processes:
            raise ProcessNotFound(f"KxProcess '{kx_process_identifier}' not found.")
        if config is None:
            config = {}
        if strategy_name not in self.strategies:
            raise StrategyNotRegistered(f"Strategy {strategy_name} was not registered. Please register using "
                                        f"'self.register_strategy' method.")
        try:
            response = self.ipc_server.send_blocking_request(kx_process_identifier, "create_worker",
                                                             {"strategy_name": strategy_name,
                                                              "identifier": worker_identifier,
                                                              "config": config})
            if response["status"] == "error":
                ex = deserialize(response["return"])
                raise ex
        except (SocketServerSendError, SocketServerClientNotFound, StrategyNotFoundError,
                WorkerAlreadyExistsError, GenericException) as e:
            raise e.add_ctx(f"Error from KuiX core while creating a new worker for strategy: '{strategy_name}'")

    @configured
    def start_worker(self, kx_process_identifier, worker_identifier: str):
        """
        Call the '__start__' method of a worker.
        :param kx_process_identifier: Identifier of the KX process to use.
        :param worker_identifier: Identifier of the worker.

        :raises ProcessNotFound: if the KxProcess was not found.
        :raises SocketServerSendError: if an error occurred while sending the request to the KxProcess.
        :raises SocketServerClientNotFound: if the KxProcess was not found.
        :raises WorkerNotFoundError: if the worker was not found in the KxProcess.
        :raises GenericException: if an error occurred while starting the worker in the KxProcess.
        To get more details as a developer, look at the 'initial_type' and 'initial_msg' attributes of the
        raised exception.
        """
        if kx_process_identifier not in self.kx_processes:
            raise ProcessNotFound(f"KxProcess '{kx_process_identifier}' not found.")
        try:
            response = self.ipc_server.send_blocking_request(kx_process_identifier, "start_worker",
                                                             {"identifier": worker_identifier})
            if response["status"] == "error":
                ex = deserialize(response["return"])
                raise ex
        except (SocketServerSendError, SocketServerClientNotFound, WorkerNotFoundError, GenericException) as e:
            raise e.add_ctx(f"Error from KuiX core while starting worker '{worker_identifier}' instanced on process "
                            f"'{kx_process_identifier}'")

    @configured
    def stop_worker(self, kx_process_identifier, worker_identifier: str):
        """
        Call the '__stop__' method of a worker.
        :param kx_process_identifier: Identifier of the KX process to use.
        :param worker_identifier: Identifier of the worker.

        :raises ProcessNotFound: if the KxProcess was not found.
        :raises SocketServerSendError: if an error occurred while sending the request to the KxProcess.
        :raises SocketServerClientNotFound: if the KxProcess was not found.
        :raises WorkerNotFoundError: if the worker was not found in the KxProcess.
        :raises GenericException: if an error occurred while starting the worker in the KxProcess.
        To get more details as a developer, look at the 'initial_type' and 'initial_msg' attributes of the
        raised exception.
        """
        if kx_process_identifier not in self.kx_processes:
            raise ProcessNotFound(f"KxProcess '{kx_process_identifier}' not found.")
        try:
            response = self.ipc_server.send_blocking_request(kx_process_identifier, "stop_worker",
                                                             {"identifier": worker_identifier})
            if response["status"] == "error":
                ex = deserialize(response["return"])
                raise ex
        except (SocketServerSendError, SocketServerClientNotFound, WorkerNotFoundError, GenericException) as e:
            raise e.add_ctx(f"Error from KuiX core while stopping worker '{worker_identifier}' instanced on process "
                            f"'{kx_process_identifier}'")

    @configured
    def close_worker(self, kx_process_identifier, worker_identifier: str):
        """
        Call the '__close__' method of a worker.
        :param kx_process_identifier: Identifier of the KX process to use.
        :param worker_identifier: Identifier of the worker.

        :raises ProcessNotFound: if the KxProcess was not found.
        :raises SocketServerSendError: if an error occurred while sending the request to the KxProcess.
        :raises SocketServerClientNotFound: if the KxProcess was not found.
        :raises WorkerNotFoundError: if the worker was not found in the KxProcess.
        :raises GenericException: if an error occurred while starting the worker in the KxProcess.
        To get more details as a developer, look at the 'initial_type' and 'initial_msg' attributes of the
        raised exception.
        """
        if kx_process_identifier not in self.kx_processes:
            raise ProcessNotFound(f"KxProcess '{kx_process_identifier}' not found.")
        try:
            response = self.ipc_server.send_blocking_request(kx_process_identifier, "close_worker",
                                                             {"identifier": worker_identifier})
            if response["status"] == "error":
                ex = deserialize(response["return"])
                raise ex
        except (SocketServerSendError, SocketServerClientNotFound, WorkerNotFoundError, GenericException) as e:
            raise e.add_ctx(f"Error from KuiX core while closing worker '{worker_identifier}' instanced on process "
                            f"'{kx_process_identifier}'")

    # --- PROCESS COMPONENTS ---
    @configured
    def register_process_component(self, name: str, import_path: str, config=None):
        """
        Register a process component.
        :param name: Name of the process component, this have to be the name of the class to import.
        :param import_path: Absolute path of the module file where the process component is located.
        :param config: Configuration dict to provide to the process component '__init__' method.

        :raises StrategyAlreadyRegistered: if a strategy with the same name already exists.
        :raises SocketServerSendError: if an error occurred while sending the data to the process, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        :raises SocketServerClientNotFound: if the client was not found.
        :raises KxProcessStrategyImportError: if an error occurred while importing the strategy on the KxProcess.
        """
        if config is None:
            config = {}
        if name in self.process_components:
            raise ProcessComponentAlreadyRegistered(f"Component '{name}' already registered.")
        self.process_components[name] = [import_path, config]
        # Push the strategy to all processes
        for process in self.kx_processes:
            try:
                response = self.ipc_server.send_blocking_request(process, "add_component",
                                                                 {"name": name, "import_path": import_path,
                                                                  "config": config})
                if response["status"] == "error":
                    # deserialize exception
                    ex = deserialize(response["return"])
                    raise ex
            except (SocketServerSendError, SocketServerClientNotFound, KeyError,
                    KxProcessComponentInitError, KxProcessComponentImportError) as e:
                LOGGER.error_exception(e.add_ctx(f"Error from KuiX core while registering process component "
                                                 f"'{name}'"), CORE)
