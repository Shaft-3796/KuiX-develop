"""
This file implements a class to manage a KxProcess running process components and workers.
"""
import multiprocessing

from src.core.Utils import Endpoint, BlockingEndpoint
from src.core.ipc.IpcClient import IpcClient
from src.core.Exceptions import *
from src.core.Logger import LOGGER, CORE


class KxProcess:

    def __init__(self, identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):

        # Process
        self.pid = multiprocessing.current_process().pid

        # Args
        self.identifier = identifier
        self.auth_key = auth_key
        self.host = host
        self.port = port
        self.artificial_latency = artificial_latency

        # IPC setup
        try:
            self.ipc = IpcClient(identifier, auth_key, host, port, artificial_latency)
        except SocketClientConnectionError as e:
            raise e.add_note(f"KxProcess '{identifier}' setup error.")

        # Strategies
        # Hold strategies classes to instance workers
        self.strategies = {}  # type dict[name: str, type]

        # Workers
        # Hold workers (strategies instances)
        self.workers = {}  # type dict[identifier: str, instance of strategy]

        # Register native remote endpoint.
        # Register remote endpoints
        for method in [getattr(self, method_name) for method_name in dir(self)
                       if callable(getattr(self, method_name))]:
            if hasattr(method, "faf_endpoint"):
                self.ipc.endpoints[(method, "faf_endpoint")] = method
            if hasattr(method, "blocking_endpoint"):
                self.ipc.endpoints[(method, "blocking_endpoint")] = method

        LOGGER.info(f"KxProcess '{identifier}' setup complete.", CORE)

    def __destruct_process__(self):
        # Try to close properly the process and all components
        for worker in self.workers.values():
            try:
                worker.destruct_worker()
            except BaseException as e:
                LOGGER.error_exception(cast(e, WorkerMethodCallError).add_note(f"KxProcess '{self.identifier}': "
                                                                               f"error while destructing a worker "
                                                                               f"during"
                                                                               f"_destruct_process."), CORE)
        try:
            self.ipc.close()
        except SocketClientCloseError as e:
            LOGGER.error_exception(e.add_note(f"KxProcess '{self.identifier}': "
                                              f"error while closing the IPC client during _destruct_process."), CORE)
        # Finally, kill the process
        multiprocessing.current_process().terminate()

    # --- Workers and strategies management ---
    def register_strategy(self, name: str, import_path: str):
        # Import strategy
        try:
            strategy = __import__(import_path, fromlist=[name])
        except BaseException as e:
            raise KxProcessStrategyImportError(e).add_note(f"KxProcess {self.identifier} _register_strategy: "
                                                           f"unable to import strategy at {import_path}")
        # Register strategy
        self.strategies[name] = strategy

    def create_worker(self, strategy_name: str, identifier: str, config: dict):
        # Check if strategy is registered
        if strategy_name not in self.strategies:
            raise StrategyNotFoundError().add_note(f"KxProcess {self.identifier} _create_worker: strategy "
                                                   f"'{strategy_name}' not found.")

        # Check if the worker already exists
        if identifier in self.workers:
            raise WorkerAlreadyExistsError().add_note(f"KxProcess {self.identifier} _create_worker: worker "
                                                      f"'{identifier}' already exists.")
        # Create worker
        try:
            worker = self.strategies[strategy_name](identifier, config)
        except BaseException as e:
            raise cast(e).add_note(f"KxProcess {self.identifier} _create_worker: worker '{identifier}' failed to init.")

        # Register worker
        self.workers[identifier] = worker

    def start_worker(self, identifier: str):
        # Check if worker exists
        if identifier not in self.workers:
            raise WorkerNotFoundError().add_note(f"KxProcess {self.identifier} _start_worker: worker "
                                                 f"'{identifier}' not found.")
        # Start worker
        try:
            self.workers[identifier].start()
        except BaseException as e:
            raise cast(e, WorkerInitError).add_note(f"KxProcess {self.identifier} _start_worker: worker '{identifier}' "
                                                    f"failed to start.")

    def stop_worker(self, identifier: str):
        # Check if worker exists
        if identifier not in self.workers:
            raise WorkerNotFoundError().add_note(f"KxProcess {self.identifier} _start_worker: worker "
                                                 f"'{identifier}' not found.")
        # Stop worker
        try:
            self.workers[identifier].stop()
        except BaseException as e:
            raise cast(e, WorkerMethodCallError).add_note(f"KxProcess {self.identifier} _start_worker: worker "
                                                          f"'{identifier}' failed to stop.")

    def destruct_worker(self, identifier: str):
        # Check if worker exists
        if identifier not in self.workers:
            raise WorkerNotFoundError().add_note(f"KxProcess {self.identifier} _start_worker: worker "
                                                 f"'{identifier}' not found.")
            # Destruct worker
        try:
            self.workers[identifier].destruct()
            del self.workers[identifier]
        except BaseException as e:
            raise cast(e, WorkerMethodCallError).add_note(
                f"KxProcess {self.identifier} _start_worker: worker '{identifier}' "
                f"failed to being destructed.")

    # --- IPC management ---
    def register_endpoint(self, name: str, callback: callable):
        self.ipc.endpoints[name] = callback

    def register_blocking_endpoint(self, name: str, callback: callable):
        self.ipc.blocking_endpoints[name] = callback

    def send(self, endpoint: str, data: dict):
        try:
            self.ipc.send_fire_and_forget_request(endpoint, data)
        except SocketClientSendError as e:
            raise e.add_note(f"KxProcess {self.identifier} _ipc_send: error while sending data to "
                             f"endpoint '{endpoint}'.")

    def send_and_block(self, endpoint: str, data: dict):
        try:
            return self.ipc.send_blocking_request(endpoint, data)
        except SocketClientSendError as e:
            raise e.add_note(f"KxProcess {self.identifier} _ipc_send: error while sending data to blocking "
                             f"endpoint '{endpoint}'.")

    # --- Native Endpoints ---
    @BlockingEndpoint("register_strategy")
    def __remote_register_strategy__(self, rid: str, data: dict):
        try:
            self.register_strategy(data["name"], data["import_path"])
            ret_data = {"status": "success", "return": "Successfully registered strategy."}
        except KxProcessStrategyImportError as e:
            ret_data = {"status": "error", "return": serialize(e)}
        self.ipc.send_response("register_strategy", ret_data, rid)

    @BlockingEndpoint("create_worker")
    def __remote_create_worker__(self, rid: str, data: dict):
        try:
            self.create_worker(data["strategy_name"], data["identifier"], data["config"])
            ret_data = {"status": "success", "return": "Successfully created worker."}
        except StrategyNotFoundError or WorkerAlreadyExistsError or GenericException as e:
            ret_data = {"status": "error", "return": serialize(e)}
        self.ipc.send_response("create_worker", ret_data, rid)

    @BlockingEndpoint("start_worker")
    def __remote_start_worker__(self, rid: str, data: dict):
        try:
            self.start_worker(data["identifier"])
            ret_data = {"status": "success", "return": "Successfully started worker."}
        except WorkerNotFoundError or GenericException as e:
            ret_data = {"status": "error", "return": serialize(e)}
        self.ipc.send_response("start_worker", ret_data, rid)

    @BlockingEndpoint("stop_worker")
    def __remote_stop_worker__(self, rid: str, data: dict):
        try:
            self.stop_worker(data["identifier"])
            ret_data = {"status": "success", "return": "Successfully stopped worker."}
        except WorkerNotFoundError or GenericException as e:
            ret_data = {"status": "error", "return": serialize(e)}
        self.ipc.send_response("stop_worker", ret_data, rid)

    @BlockingEndpoint("destruct_worker")
    def __remote_destruct_worker__(self, rid: str, data: dict):
        try:
            self.destruct_worker(data["identifier"])
            ret_data = {"status": "success", "return": "Successfully destructed worker."}
        except WorkerNotFoundError or GenericException as e:
            ret_data = {"status": "error", "return": serialize(e)}
        self.ipc.send_response("destruct_worker", ret_data, rid)

    @Endpoint("destruct_process")
    def __remote_destruct_process__(self, data: dict):
        self.__destruct_process__()


def __launch__(identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
               artificial_latency: float = 0.1):
    # IN A SUBPROCESS
    try:
        # Create process
        process = KxProcess(identifier, auth_key, host, port, artificial_latency)
    except SocketClientConnectionError as e:
        raise e.add_note(f"KxProcess '{identifier}' launch: error while creating the KxProcess.")

# TODO: add some info logs and trace.
