"""
This module exposes methods and functionalities of KuiX through an API.
"""
import multiprocessing
from src.core.Utils import KXException, Endpoint, BlockingEndpoint


class ProcessApi:
    """
    This class exposes methods and functionalities of KuiX through an API.
    """

    def __init__(self, kx_process):
        self.process = kx_process

        # Register remote endpoints
        for method in [getattr(self, method_name) for method_name in dir(self)
                       if callable(getattr(self, method_name))]:
            if hasattr(method, "faf_endpoint"):
                self.register_endpoint(getattr(method, "faf_endpoint"), method)
            if hasattr(method, "blocking_endpoint"):
                self.register_blocking_endpoint(getattr(method, "blocking_endpoint"), method)

    # --- Process management ---
    def get_process(self):
        """
        Returns the process.
        :return: The process object.
        """
        return self.process

    def get_process_identifier(self):
        """
        Get the name of the process.
        :return: The name of the process.
        """
        return self.process.identifier

    # --- Workers and strategies management ---
    def register_strategy(self, name: str, import_path: str):
        """
        Register a strategy.
        :param name: The name of the strategy.
        :param import_path: The import path of the strategy.
        """
        self.process._register_strategy(name, import_path)

    def create_worker(self, strategy_name: str, identifier: str, config: dict):
        """
        Create a worker.
        :param strategy_name: The name of the strategy.
        :param identifier: The identifier of the worker.
        :param config: The configuration of the worker.
        """
        self.process._create_worker(strategy_name, identifier, config)

    def start_worker(self, identifier: str):
        """
        Start a worker.
        :param identifier: The identifier of the worker.
        """
        self.process._start_worker(identifier)

    def stop_worker(self, identifier: str):
        """
        Stop a worker.
        :param identifier: The identifier of the worker.
        """
        self.process._stop_worker(identifier)

    def destruct_worker(self, identifier: str):
        """
        Destruct a worker.
        :param identifier: The identifier of the worker.
        """
        self.process._destruct_worker(identifier)

    # --- IPC ---
    def register_endpoint(self, endpoint_name: str, callback: callable):
        """
        Register an endpoint.
        :param endpoint_name: The name of the endpoint.
        :param callback: The callback of the endpoint.
        """
        self.process._register_endpoint(endpoint_name)

    def register_blocking_endpoint(self, endpoint_name: str, callback: callable):
        """
        Register a blocking endpoint.
        :param endpoint_name: The name of the endpoint.
        :param callback: The callback of the endpoint.
        """
        self.process._register_blocking_endpoint(endpoint_name)

    def send(self, endpoint_name: str, data: dict):
        """
        Send data to an endpoint.
        :param endpoint_name: The name of the endpoint.
        :param data: The data to send.
        """
        self.process._ipc_send(endpoint_name, data)

    def send_and_block(self, endpoint_name: str, data: dict, block: bool = True):
        """
        Send data to an endpoint and wait for a response.
        :param endpoint_name: The name of the endpoint.
        :param data: The data to send.
        :param block: Whether to really block and wait for a response.
        :return: The response.
        """
        return self.process._ipc_send_blocking(endpoint_name, data, block)

    # --- REMOTE IPC CALLS ---
    @Endpoint("register_strategy")
    def _remote_register_strategy(self, process_identifier: str, data: dict):
        self.register_strategy(data["name"], data["import_path"])

    @Endpoint("create_worker")
    def _remote_create_worker(self, process_identifier: str, data: dict):
        self.create_worker(data["strategy_name"], data["identifier"], data["config"])

    @Endpoint("start_worker")
    def _remote_start_worker(self, process_identifier: str, data: dict):
        self.start_worker(data["identifier"])

    @Endpoint("stop_worker")
    def _remote_stop_worker(self, process_identifier: str, data: dict):
        self.stop_worker(data["identifier"])

    @Endpoint("destruct_worker")
    def _remote_destruct_worker(self, process_identifier: str, data: dict):
        self.destruct_worker(data["identifier"])

    @Endpoint("destruct_process")
    def _remote_destruct_process(self, process_identifier: str, data: dict):
        self.process._destruct_process()


