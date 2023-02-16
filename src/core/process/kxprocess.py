"""
This file implements a class to manage a KxProcess running process components and workers.
"""
import multiprocessing

from src.core.Logger import LOGGER, CORE, KXException
from src.core.ipc.IpcClient import IpcClient
from src.core.API import ProcessApi


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
        except Exception as e:
            e.add_traceback(f"KxProcess {identifier} init")
            raise e

        # Strategies
        # Hold strategies classes to instance workers
        self.strategies = {}  # type dict[name: str, type]

        # Workers
        # Hold workers (strategies instances)
        self.workers = {}  # type dict[identifier: str, instance of strategy]

        # API exposing
        self.api = ProcessApi(self)

    def _destruct_process(self):
        # Try to close properly the process and all components
        for worker in self.workers.values():
            worker.destruct_worker()
        self.ipc.close()
        # Finally, kill the process
        multiprocessing.current_process().terminate()

    # --- Workers and strategies management ---
    def _register_strategy(self, name: str, import_path: str):
        try:
            # Import strategy
            strategy = __import__(import_path, fromlist=[name])
            # Register strategy
            self.strategies[name] = strategy
        except Exception as e:
            raise KXException(e, f"KxProcess {self.identifier} _register_strategy")

    def _create_worker(self, strategy_name: str, identifier: str, config: dict):
        try:
            # Check if strategy is registered
            if strategy_name not in self.strategies:
                raise KXException(ValueError(), f"KxProcess {self.identifier} _create_worker: strategy {strategy_name} "
                                                f"not registered")
            # Create worker
            worker = self.strategies[strategy_name](identifier, config)
            if identifier in self.workers:
                raise KXException(ValueError(), f"KxProcess {self.identifier} _create_worker: worker {identifier} "
                                                f"already exists")
            # Register worker
            self.workers[identifier] = worker
        except Exception as e:
            raise KXException(e, f"KxProcess {self.identifier} _create_worker")

    def _start_worker(self, identifier: str):
        try:
            # Check if worker exists
            if identifier not in self.workers:
                raise KXException(ValueError(), f"KxProcess {self.identifier} _start_worker: worker {identifier} "
                                                f"does not exist")
            # Start worker
            self.workers[identifier].start()
        except Exception as e:
            raise KXException(e, f"KxProcess {self.identifier} _start_worker")

    def _stop_worker(self, identifier: str):
        try:
            # Check if worker exists
            if identifier not in self.workers:
                raise KXException(ValueError(), f"KxProcess {self.identifier} _stop_worker: worker {identifier} "
                                                f"does not exist")
            # Stop worker
            self.workers[identifier].stop()
        except Exception as e:
            raise KXException(e, f"KxProcess {self.identifier} _stop_worker")

    def _destruct_worker(self, identifier: str):
        try:
            # Check if worker exists
            if identifier not in self.workers:
                raise KXException(ValueError(), f"KxProcess {self.identifier} _destruct_worker: worker {identifier} "
                                                f"does not exist")
            # Destruct worker
            self.workers[identifier].destruct()
            del self.workers[identifier]
        except Exception as e:
            raise KXException(e, f"KxProcess {self.identifier} _destruct_worker")

    # --- IPC management ---
    def _ipc_register_endpoint(self, name: str, callback: callable):
        try:
            self.ipc.endpoints[name] = callback
        except Exception as e:
            raise KXException(e, f"KxProcess {self.identifier} _ipc_register_endpoint")

    def _ipc_register_blocking_endpoint(self, name: str, callback: callable):
        try:
            self.ipc.blocking_endpoints[name] = callback
        except Exception as e:
            raise KXException(e, f"KxProcess {self.identifier} _ipc_register_blocking_endpoint")

    def _ipc_send(self, endpoint: str, data: dict):
        try:
            self.ipc.send_fire_and_forget_request(endpoint, data)
        except Exception as e:
            raise KXException(e, f"KxProcess {self.identifier} _ipc_send")

    def _ipc_send_and_block(self, endpoint: str, data: dict, block: bool = True):
        try:
            return self.ipc.send_blocking_request(endpoint, data, block)
        except Exception as e:
            raise KXException(e, f"KxProcess {self.identifier} _ipc_send_and_block")


def launch(identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
           artificial_latency: float = 0.1):
    # IN A SUBPROCESS
    try:
        # Create process
        process = KxProcess(identifier, auth_key, host, port, artificial_latency)
        # Start process
        process.ipc.connect()
    except Exception as e:
        e.add_traceback(f"KxProcess {identifier} launch")
        raise e
