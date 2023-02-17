"""
This file implements a class to manage a KxProcess running process components and workers.
"""
import multiprocessing

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

        LOGGER.info(f"KxProcess '{identifier}' setup complete.", CORE)

    def _destruct_process(self):
        # Try to close properly the process and all components
        for worker in self.workers.values():
            try:
                worker.destruct_worker()
            except Exception as e:
                LOGGER.error_exception(cast(e).add_note(f"KxProcess '{self.identifier}': "
                                                        f"error while destructing a worker during "
                                                        f"_destruct_process."), CORE)
        try:
            self.ipc.close()
        except SocketClientCloseError as e:
            LOGGER.error_exception(e.add_note(f"KxProcess '{self.identifier}': "
                                              f"error while closing the IPC client during _destruct_process."), CORE)
        # Finally, kill the process
        multiprocessing.current_process().terminate()

    # --- Workers and strategies management ---
    def _register_strategy(self, name: str, import_path: str):
        # Import strategy
        try:
            strategy = __import__(import_path, fromlist=[name])
        except Exception as e:
            raise KxProcessStrategyImportError(e).add_note(f"KxProcess {self.identifier} _register_strategy: "
                                                           f"unable to import strategy at {import_path}")
        # Register strategy
        self.strategies[name] = strategy

    def _create_worker(self, strategy_name: str, identifier: str, config: dict):
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
        except Exception as e:
            raise cast(e).add_note(f"KxProcess {self.identifier} _create_worker: worker '{identifier}' failed to init.")

        # Register worker
        self.workers[identifier] = worker

    def _start_worker(self, identifier: str):
        # Check if worker exists
        if identifier not in self.workers:
            raise WorkerNotFoundError().add_note(f"KxProcess {self.identifier} _start_worker: worker "
                                                 f"'{identifier}' not found.")
        # Start worker
        try:
            self.workers[identifier].start()
        except Exception as e:
            raise cast(e).add_note(f"KxProcess {self.identifier} _start_worker: worker '{identifier}' failed to start.")

    def _stop_worker(self, identifier: str):
        # Check if worker exists
        if identifier not in self.workers:
            raise WorkerNotFoundError().add_note(f"KxProcess {self.identifier} _start_worker: worker "
                                                 f"'{identifier}' not found.")
        # Stop worker
        try:
            self.workers[identifier].stop()
        except Exception as e:
            raise cast(e).add_note(f"KxProcess {self.identifier} _start_worker: worker '{identifier}' failed to stop.")

    def _destruct_worker(self, identifier: str):
        # Check if worker exists
        if identifier not in self.workers:
            raise WorkerNotFoundError().add_note(f"KxProcess {self.identifier} _start_worker: worker "
                                                f"'{identifier}' not found.")
            # Destruct worker
        try:
            self.workers[identifier].destruct()
            del self.workers[identifier]
        except Exception as e:
            raise cast(e).add_note(f"KxProcess {self.identifier} _start_worker: worker '{identifier}' "
                                   f"failed to being destructed.")

    # --- IPC management ---
    def _ipc_register_endpoint(self, name: str, callback: callable):
        self.ipc.endpoints[name] = callback

    def _ipc_register_blocking_endpoint(self, name: str, callback: callable):
        self.ipc.blocking_endpoints[name] = callback

    def _ipc_send(self, endpoint: str, data: dict):
        try:
            self.ipc.send_fire_and_forget_request(endpoint, data)
        except SocketClientSendError as e:
            raise e.add_note(f"KxProcess {self.identifier} _ipc_send: error while sending data to "
                             f"endpoint '{endpoint}'.")

    def _ipc_send_and_block(self, endpoint: str, data: dict):
        try:
            return self.ipc.send_blocking_request(endpoint, data)
        except SocketClientSendError as e:
            raise e.add_note(f"KxProcess {self.identifier} _ipc_send: error while sending data to blocking "
                             f"endpoint '{endpoint}'.")


def launch(identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
           artificial_latency: float = 0.1):
    # IN A SUBPROCESS
    try:
        # Create process
        process = KxProcess(identifier, auth_key, host, port, artificial_latency)
    except SocketClientConnectionError as e:
        raise e.add_note(f"KxProcess '{identifier}' launch: error while creating the KxProcess.")

# TODO: add some info logs and trace.