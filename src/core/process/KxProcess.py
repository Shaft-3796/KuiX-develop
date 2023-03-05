"""
This file implements a class to manage a KxProcess running process components and workers.
"""
import multiprocessing
import os
import signal
from inspect import signature

from src.core.Utils import Endpoint, BlockingEndpoint, Respond
from src.core.ipc.IpcClient import IpcClient
from src.core.Exceptions import *
from src.core.Logger import LOGGER, CORE
import importlib.util
import sys

from src.process_components.BaseProcessComponent import BaseProcessComponent


class KxProcess:

    def __init__(self, identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
                 artificial_latency: float = 0.1):
        """
        Instance a KxProcess to host workers.
        :param identifier: Unique identifier of the process.
        :param auth_key: Authentication key to connect to the server.
        :param host: host of the server.
        :param port: port of the server.
        :param artificial_latency: Time in s between each .recv call for a connection. Default is 0.1s.
        This is used to prevent the CPU from being overloaded. Change this value if you know what you're doing.

        :raise SocketClientConnectionError: If the client failed to connect to the server, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """

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
            raise e.add_ctx(f"KxProcess '{identifier}' setup error.")

        # Process components
        self.components = {}  # type dict[name: str, instance]

        # Strategies
        # Hold strategies classes to instance workers
        self.strategies = {}  # type dict[name: str, type]

        # Workers
        # Hold workers (strategies instances)
        self.workers = {}  # type dict[identifier: str, instance of strategy]

        # Register native remote endpoint.
        for method in [getattr(self, method_name) for method_name in dir(self)
                       if callable(getattr(self, method_name))]:
            if hasattr(method, "faf_endpoint"):
                self.ipc.endpoints[getattr(method, "faf_endpoint")] = method
            if hasattr(method, "blocking_endpoint"):
                self.ipc.blocking_endpoints[getattr(method, "blocking_endpoint")] = method

        LOGGER.info(f"KxProcess '{identifier}' setup complete.", CORE)

        # Placeholder for worker endpoints
        self.worker_endpoints = {}  # dict[name: str, dict[worker_id: str, callback: function]]
        self.worker_blocking_endpoints = {}  # dict[name: str, dict[worker_id: str, callback: function]]

    def __close_process__(self, rid):
        """
        This method try to close and close properly all workers and components of the process.
        Then the process is self-killed.
        """
        # Try to close properly the process and all components
        for worker in self.workers.values():
            try:
                worker.close_worker()
            except Exception as e:
                LOGGER.error_exception(cast(e, f"KxProcess '{self.identifier}': "
                                               f"error while closing a worker "
                                               f"during"
                                               f"_close_process, look at the initial exception for more details.",
                                            WorkerMethodCallError), CORE)

        # Final response
        self.ipc.send_response("close_process", {"status": "success", "return": "Successfully killed process."}, rid)

        try:
            self.ipc.close()
        except SocketClientCloseError as e:
            LOGGER.error_exception(e.add_ctx(f"KxProcess '{self.identifier}': "
                                             f"error while closing the IPC client during _close_process."), CORE)
        # Finally, kill the process
        LOGGER.info(f"KxProcess '{self.identifier}': killing the process.", CORE)
        os.kill(os.getpid(), signal.SIGKILL)

    # --- Components ---
    def add_component(self, name: str, import_path: str, config: dict = None):
        """
        Register a component to be used by the process.
        :param name: Name of the component, actually the name of the class.
        :param import_path: Path to the module containing the component class.
        :param config: Configuration to pass to the component '__init__' method.
        """
        if name in self.components:
            return  # Already registered
        try:
            spec = importlib.util.spec_from_file_location("ExternalComponent", import_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules["ExternalComponent"] = module
            spec.loader.exec_module(module)
            comp = getattr(module, name)
        except Exception as e:
            raise KxProcessComponentImportError(f"KxProcess {self.identifier} 'add_component': "
                                                f"unable to import component at {import_path}, "
                                                f"look at the initial exception for more details.") + e
        # Register strategy
        try:
            component = comp(self, config)
            if not isinstance(component, BaseProcessComponent):
                LOGGER.warning(
                    f"KxProcess {self.identifier} tried to add a component that is not "
                    f"an instance of BaseProcessComponent. This can lead to unexpected behaviours, inheritance "
                    f"from BaseProcessComponent is recommended.")
            self.components[name] = component
            LOGGER.trace(f"KxProcess '{self.identifier}': component '{name}' added.", CORE)
        except Exception as e:
            raise KxProcessComponentInitError(f"KxProcess {self.identifier} 'add_component': "
                                              f"unable to init component {name}, "
                                              f"look at the initial exception for more details.") + e

    # --- Workers and strategies management ---
    def register_strategy(self, name: str, import_path: str):
        """
        Register a strategy to be used by the process.
        :param name: Name of the strategy, this have to be the name of the class to import.
        :param import_path: Absolute path of the module file where the strategy is located.

        :raise KxProcessStrategyImportError: If the strategy can't be imported, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        try:
            spec = importlib.util.spec_from_file_location("ExternalStrategy", import_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules["ExternalStrategy"] = module
            spec.loader.exec_module(module)
            strategy = getattr(module, name)
        except Exception as e:
            raise KxProcessStrategyImportError(f"KxProcess {self.identifier} _register_strategy: "
                                               f"unable to import strategy at {import_path}, "
                                               f"look at the initial exception for more details.") + e
        # Register strategy
        self.strategies[name] = strategy
        LOGGER.trace(f"KxProcess '{self.identifier}': strategy '{name}' registered.", CORE)

    def create_worker(self, strategy_name: str, identifier: str, config: dict):
        """
        Instance a worker from a strategy class.
        :param strategy_name: name of the strategy to use.
        Actually the name of the class you passed to register_strategy.
        :param identifier: Unique identifier of the worker.
        :param config: A dictionary containing all arguments to pass to the strategy __init__ method.

        :raise StrategyNotFoundError: If the strategy is not registered.
        :raise WorkerAlreadyExistsError: If the worker already exists.
        :raise WorkerInitError: If the worker can't be initialized, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        :raise GenericException: If the worker can't be initialized, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        # Create worker
        try:
            # Check if strategy is registered
            if strategy_name not in self.strategies:
                raise StrategyNotFoundError(f"KxProcess {self.identifier} _create_worker: strategy "
                                            f"'{strategy_name}' not found.")

            # Check if the worker already exists
            if identifier in self.workers:
                raise WorkerAlreadyExistsError(f"KxProcess {self.identifier} _create_worker: worker "
                                               f"'{identifier}' already exists.")
            if config != {}:
                worker = self.strategies[strategy_name](identifier, config)
            else:
                worker = self.strategies[strategy_name](identifier)
        except Exception as e:
            raise cast(e, e_type=WorkerInitError, msg=f"KxProcess {self.identifier} _create_worker: worker "
                                                      f"'{identifier}' failed to init.")

        # Register worker
        self.workers[identifier] = worker
        LOGGER.trace(f"KxProcess '{self.identifier}': worker '{identifier}' created.", CORE)

    def start_worker(self, identifier: str):
        """
        Call the __start__ method of a worker.
        :param identifier: Identifier of the worker.

        :raise WorkerNotFoundError: If the worker is not registered.
        :raise WorkerMethodCallError: If the worker can't be started, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        :raise GenericException: If the worker can't be started, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        # Start worker
        try:
            # Check if worker exists
            if identifier not in self.workers:
                raise WorkerNotFoundError(f"KxProcess {self.identifier} _start_worker: worker "
                                          f"'{identifier}' not found.")
            self.workers[identifier].__start__()
        except Exception as e:
            raise cast(e, e_type=WorkerMethodCallError, msg=f"KxProcess {self.identifier} _start_worker: "
                                                            f"worker '{identifier}' failed to start.")

        LOGGER.trace(f"KxProcess '{self.identifier}': worker '{identifier}' started.", CORE)

    def stop_worker(self, identifier: str):
        """
        Call the __stop__ method of a worker.
        :param identifier: Identifier of the worker.

        :raise WorkerNotFoundError: If the worker is not registered.
        :raise WorkerMethodCallError: If the worker can't be stopped, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        :raise GenericException: If the worker can't be stopped, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        # Stop worker
        try:
            # Check if worker exists
            if identifier not in self.workers:
                raise WorkerNotFoundError(f"KxProcess {self.identifier} _stop_worker: worker "
                                          f"'{identifier}' not found.")
            self.workers[identifier].__stop__()
        except Exception as e:
            raise cast(e, e_type=WorkerMethodCallError, msg=f"KxProcess {self.identifier} _stop_worker: worker "
                                                            f"'{identifier}' failed to stop.")

        LOGGER.trace(f"KxProcess '{self.identifier}': worker '{identifier}' stopped.", CORE)

    def close_worker(self, identifier: str):
        """
        Call the __close__ method of a worker.
        :param identifier: Identifier of the worker.

        :raise WorkerNotFoundError: If the worker is not registered.
        :raise WorkerMethodCallError: If the worker can't be closed, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        :raise GenericException: If the worker can't be closed, you can access the initial
        exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised exception.
        """
        # close worker
        try:
            # Check if worker exists
            if identifier not in self.workers:
                raise WorkerNotFoundError(f"KxProcess {self.identifier} _start_worker: worker "
                                          f"'{identifier}' not found.")
            self.workers[identifier].__close__()
            del self.workers[identifier]
        except Exception as e:
            raise cast(e, e_type=WorkerMethodCallError, msg=f"KxProcess {self.identifier} _close_worker: worker "
                                                            f"'{identifier}' failed to being closed.")

        LOGGER.trace(f"KxProcess '{self.identifier}': worker '{identifier}' closed.", CORE)

    # --- Socket Events ---
    def register_on_connection_accepted_event(self, callback: callable):
        """
        Register an event, the callback will be called when the server/core authorize the connection.
        :param callback: A callable to call when the event is triggered (the callback must only have the 'identifier'
        parameter which is the identifier of the client).

        :raise EventSubscriptionError: If the callback is not callable or if it has more than one parameter.
        """
        # Check if the callback is callable and if it has only the identifier parameter:
        if not callable(callback):
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_accepted_event': callback must be a function")
        if len(signature(callback).parameters) != 1:
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_accepted_event': callback must only have one single "
                                         f"parameter named 'identifier'.")
        # Check if the parameter is named identifier
        if list(signature(callback).parameters.keys())[0] != "identifier":
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_accepted_event': the parameter of callback function "
                                         f"has to be named 'identifier'.")

        self.ipc.register_on_connection_accepted(callback)

    def register_on_connection_refused_event(self, callback: callable):
        """
        Register an event, the callback will be called when the server/core refuse the connection.
        :param callback: A callable to call when the event is triggered (the callback must only have the 'identifier'
        parameter which is the identifier of the client).

        :raise EventSubscriptionError: If the callback is not callable or if it has more than one parameter.
        """
        # Check if the callback is callable and if it has only the identifier parameter:
        if not callable(callback):
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_refused_event': callback must be a function")
        if len(signature(callback).parameters) != 1:
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_refused_event': callback must only have one single "
                                         f"parameter named 'identifier'.")
        # Check if the parameter is named identifier
        if list(signature(callback).parameters.keys())[0] != "identifier":
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_refused_event': the parameter of callback function "
                                         f"has to be named 'identifier'.")

        self.ipc.register_on_connection_refused(callback)

    def register_on_connection_closed_event(self, callback: callable):
        """
        Register an event, the callback will be called when the server/core close the connection or just after the '
        client_close_event' was triggered by a call to 'self.ipc.close()'.
        :param callback: A callable to call when the event is triggered, the callback must only have two parameters:
        'identifier' which is the identifier of the client as a str and 'from_client' which is a bool indicating if the
        connection was closed by the client through a call to 'self.ipc.close' or by the server/core.

        :raise EventSubscriptionError: If the callback is not callable or if it has more than two parameter.
        """
        # Check if the callback is callable and if it has only the identifier parameter:
        if not callable(callback):
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_closed_event': callback must be a function")
        if len(signature(callback).parameters) != 2:
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_closed_event': callback must only have two "
                                         f"parameter named 'identifier' and 'from_client'.")
        # Check if the parameter is named identifier
        if list(signature(callback).parameters.keys())[0] != "identifier":
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_closed_event': the first parameter of callback "
                                         f"function has to be named 'identifier'.")
        if list(signature(callback).parameters.keys())[1] != "from_client":
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_connection_closed_event': the second parameter of callback "
                                         f"function has to be named 'from_client'.")

        self.ipc.register_on_connection_closed(callback)

    def register_on_client_closed_event(self, callback: callable):
        """
        Register an event, the callback will be called when the client close the connection through a call to
        'self.ipc.close'.
        :param callback: A callable to call when the event is triggered, the callback must only have the 'identifier'
        parameter which is the identifier of the client as a str.

        :raise EventSubscriptionError: If the callback is not callable or if it has more than one parameter.
        """
        # Check if the callback is callable and if it has only the identifier parameter:
        if not callable(callback):
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_client_closed_event': callback must be a function")
        if len(signature(callback).parameters) != 1:
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_client_closed_event': callback must only have one single "
                                         f"parameter named 'identifier'.")
        # Check if the parameter is named identifier
        if list(signature(callback).parameters.keys())[0] != "identifier":
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_client_closed_event': the parameter of callback function "
                                         f"has to be named 'identifier'.")

        self.ipc.register_on_client_closed(callback)

    def register_on_message_received_event(self, callback: callable):
        """
        Register an event, the callback will be called when the client receive a message from the server/core.
        :param callback: A callable to call when the event is triggered, the callback must only have two parameters:
        'identifier' which is the identifier of the client as a str and 'data' which is the message received as a dict.

        :raise EventSubscriptionError: If the callback is not callable or if it has more than two parameter.
        """
        # Check if the callback is callable and if it has only the identifier parameter:
        if not callable(callback):
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_message_received_event': callback must be a function")
        if len(signature(callback).parameters) != 2:
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_message_received_event': callback must only have two "
                                         f"parameter named 'identifier' and 'data'.")
        # Check if the parameter is named identifier
        if list(signature(callback).parameters.keys())[0] != "identifier":
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_message_received_event': the first parameter of callback "
                                         f"function has to be named 'identifier'.")
        if list(signature(callback).parameters.keys())[1] != "data":
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_message_received_event': the second parameter of callback "
                                         f"function has to be named 'data'.")

        self.ipc.register_on_message_received(callback)

    def register_on_message_sent_event(self, callback: callable):
        """
        Register an event, the callback will be called when the client send a message to the server/core.
        :param callback: A callable to call when the event is triggered, the callback must only have two parameters:
        'identifier' which is the identifier of the client as a str and 'data' which is the message sent as a dict.

        :raise EventSubscriptionError: If the callback is not callable or if it has more than two parameter.
        """
        # Check if the callback is callable and if it has only the identifier parameter:
        if not callable(callback):
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_message_sent_event': callback must be a function")
        if len(signature(callback).parameters) != 2:
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_message_sent_event': callback must only have two "
                                         f"parameter named 'identifier' and 'data'.")
        # Check if the parameter is named identifier
        if list(signature(callback).parameters.keys())[0] != "identifier":
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_message_sent_event': the first parameter of callback "
                                         f"function has to be named 'identifier'.")
        if list(signature(callback).parameters.keys())[1] != "data":
            raise EventSubscriptionError(f"KxProcess {self.identifier}: error while calling "
                                         f"'register_on_message_sent_event': the second parameter of callback "
                                         f"function has to be named 'data'.")
        self.ipc.register_on_message_sent(callback)

    # --- IPC ---
    def register_endpoint(self, name: str, callback: callable):
        """
        Register an endpoint, a method accessible from the core through the IPC.
        :param name: Name of the endpoint.
        :param callback: Callback function to call when the endpoint is called. The callback must only have one
        parameter which is the data sent by the core as a dict.
        """
        if name in self.ipc.endpoints:
            LOGGER.warning(f"KxProcess {self.identifier} register_endpoint: endpoint '{name}' already exists, "
                           f"the first endpoint will be overwritten but this is probably an unexpected behavior.", CORE)
        self.ipc.endpoints[name] = callback

        LOGGER.trace(f"KxProcess '{self.identifier}': endpoint '{name}' registered.", CORE)

    def register_blocking_endpoint(self, name: str, callback: callable):
        """
        Register a blocking endpoint, a method accessible from the core through the IPC.
        This endpoint is blocking, the core will wait for a response.
        To send a response, decorate your callback with 'Respond('endpoint_name')' from utils module and return a
        dictionary or use directly the 'self.send_response' method.
        WARNING: This is a blocking method, it will block the core until the endpoint returns a value, if your method
        does not send a response using the 'self.send_response' method, some methods will block forever !
        :param name: Name of the endpoint.
        :param callback: Callback function to call when the endpoint is called. This function must absolutely
        call only one time the 'self.send_response' method, directly or by being decorated using the 'Respond'
        decorator.
        The callback must only have two parameters:
        'rid' which is the request id as a str and 'data' which is the data sent by the core as a dict.
        """
        if name in self.ipc.endpoints:
            LOGGER.warning(f"KxProcess {self.identifier} register_blocking_endpoint: endpoint '{name}' already exists, "
                           f"the first endpoint will be overwritten but this is probably an unexpected behavior.", CORE)
        self.ipc.blocking_endpoints[name] = callback

        LOGGER.trace(f"KxProcess '{self.identifier}': blocking endpoint '{name}' registered.", CORE)

    def register_worker_endpoint(self, name: str, worker_id: str, callback: callable):
        """
        Register a worker endpoint, a method accessible from the core through the IPC.
        This endpoint can be registered multiple times with different worker_id, when this endpoint is called by
        the core, a worker_id must being specified to call the correct callback.
        :param name: Name of the endpoint.
        :param worker_id: Unique worker identifier.
        :param callback: Callback function to call when the endpoint is called. This function must absolutely
        call only one time the 'self.send_response' method. The callback must only have two parameters:
        'rid' which is the request id as a str and 'data' which is the data sent by the core as a dict.
        """
        # If new endpoint, initialize the routing function and the callback dict.
        if name not in self.worker_endpoints:
            self.worker_endpoints[name] = {}

            # routing
            def __routing__(data: dict):
                try:
                    self.worker_endpoints[name][data["worker_id"]](data)
                except Exception as e:
                    LOGGER.error_exception(cast(e, e_type=WorkerMethodCallError, msg="KxProcess error while calling "
                                                                                     "worker endpoint"), CORE)

            if worker_id in self.worker_endpoints[name]:
                LOGGER.warning(f"KxProcess {self.identifier} register_worker_endpoint: endpoint '{name}' already "
                               f"exists for the worker '{worker_id}', the first endpoint will be overwritten but "
                               f"this is probably an unexpected behavior.", CORE)
            self.ipc.endpoints[name] = __routing__  # registering routing function as the endpoint.

        # Register the worker callback
        self.worker_endpoints[name][worker_id] = callback

        LOGGER.trace(f"KxProcess '{self.identifier}': worker endpoint '{name}' registered.", CORE)

    def register_worker_blocking_endpoint(self, name: str, worker_id: str, callback: callable):
        """
        Register a worker blocking endpoint, a method accessible from the core through the IPC.
        This endpoint can be registered multiple times with different worker_id, when this endpoint is called by
        the core, a worker_id must being specified to call the correct callback.
        This endpoint is blocking, the core will wait for the endpoint to send a response.
        To send a response, decorate your callback with 'Respond('endpoint_name')' from utils module and return a
        dictionary or use directly the 'self.send_response' method.
        WARNING: This is a blocking method, it will block the core until the endpoint returns a value, if your method
        does not send a response using the 'self.send_response' method, some methods will block forever !
        :param name: Name of the endpoint.
        :param worker_id: Unique worker identifier.
        :param callback: Callback function to call when the endpoint is called. This function must absolutely
        call only one time the 'self.send_response' method, directly or by being decorated using the 'Respond'
        decorator.
        The callback must only have two parameters: 'rid' which is the request id as a str and 'data' which is the
        data sent by the core as a dict.
        """
        # If new endpoint, initialize the routing function and the callback dict.
        if name not in self.worker_blocking_endpoints:
            self.worker_blocking_endpoints[name] = {}

            # routing
            def __routing__(rid: str, data: dict):
                try:
                    self.worker_blocking_endpoints[name][data["worker_id"]](rid, data)
                except Exception as e:
                    LOGGER.error_exception(cast(e, e_type=WorkerMethodCallError, msg=f"KxProcess '{self.identifier}' "
                                                                                     f"error while calling "
                                                                                     "worker blocking endpoint"), CORE)

            if worker_id in self.worker_endpoints[name]:
                LOGGER.warning(f"KxProcess {self.identifier} register_worker_blocking_endpoint: endpoint '{name}' "
                               f"already"
                               f"exists for the worker '{worker_id}', the first endpoint will be overwritten but "
                               f"this is probably an unexpected behavior.", CORE)
            self.ipc.blocking_endpoints[name] = __routing__  # registering routing function as the endpoint.

        # Register the worker callback
        self.worker_blocking_endpoints[name][worker_id] = callback

        LOGGER.trace(f"KxProcess '{self.identifier}': worker blocking endpoint '{name}' registered.", CORE)

    def send(self, endpoint: str, data: dict):
        """
        Send data as a dict to the core through the IPC.
        :param endpoint: Name of the endpoint to call on the core as registered with the 'register_endpoint'
        method of the core.
        :param data: Data to send as a dict

        :raises SocketClientSendError: if an error occurred while sending the data to the core, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        """
        try:
            self.ipc.send_fire_and_forget_request(endpoint, data)
        except SocketClientSendError as e:
            raise e.add_ctx(f"KxProcess {self.identifier} _ipc_send: error while sending data to "
                            f"endpoint '{endpoint}'.")

        LOGGER.trace(f"KxProcess '{self.identifier}': data sent to endpoint '{endpoint}'.", CORE)

    def send_and_block(self, endpoint: str, data: dict):
        """
        Send data as a dict to the core through the IPC and wait for the response.
        :param endpoint: Name of the endpoint to call on the core as registered with the 'register_endpoint'
        method of the core.
        :param data: Data to send as a dict

        :raises SocketClientSendError: if an error occurred while sending the data to the core, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        """
        try:
            return self.ipc.send_blocking_request(endpoint, data)
        except SocketClientSendError as e:
            raise e.add_ctx(f"KxProcess {self.identifier} _ipc_send: error while sending data to blocking "
                            f"endpoint '{endpoint}'.")

    def send_response(self, endpoint: str, data: dict, rid: str):
        """
        Send the response of a blocking request.
        :param endpoint: Name of the endpoint to call on the core as registered with the 'register_endpoint'
        :param data: Data to send as a dict
        :param rid: Request id of the request to respond to.

        :raises SocketClientSendError: if an error occurred while sending the data to the core, you can access
        the initial exception type and msg by accessing 'initial_type' and 'initial_msg' attributes of the raised
        exception.
        """
        try:
            self.ipc.send_response(endpoint, data, rid)
        except SocketClientSendError as e:
            raise e.add_ctx(f"KxProcess {self.identifier} _ipc_send_response: error while sending response to blocking "
                            f"endpoint '{endpoint}'.")

        LOGGER.trace(f"KxProcess '{self.identifier}': response sent to endpoint '{endpoint}'.", CORE)

    # --- Native Endpoints ---
    @BlockingEndpoint("register_strategy")
    @Respond("register_strategy")
    def __remote_register_strategy__(self, rid: str, data: dict):
        try:
            self.register_strategy(data["name"], data["import_path"])
            ret_data = {"status": "success", "return": "Successfully registered strategy."}
        except KxProcessStrategyImportError as e:
            ret_data = {"status": "error", "return": e.serialize()}
        return ret_data

    @BlockingEndpoint("create_worker")
    @Respond("create_worker")
    def __remote_create_worker__(self, rid: str, data: dict):
        try:
            self.create_worker(data["strategy_name"], data["identifier"], data["config"])
            ret_data = {"status": "success", "return": "Successfully created worker."}
        except (StrategyNotFoundError, WorkerAlreadyExistsError, GenericException, Exception) as e:
            ret_data = {"status": "error", "return": e.serialize()}
        return ret_data

    @BlockingEndpoint("start_worker")
    @Respond("start_worker")
    def __remote_start_worker__(self, rid: str, data: dict):
        try:
            self.start_worker(data["identifier"])
            ret_data = {"status": "success", "return": "Successfully started worker."}
        except (WorkerNotFoundError, GenericException, WorkerMethodCallError) as e:
            ret_data = {"status": "error", "return": e.serialize()}
        return ret_data

    @BlockingEndpoint("stop_worker")
    @Respond("stop_worker")
    def __remote_stop_worker__(self, rid: str, data: dict):
        try:
            self.stop_worker(data["identifier"])
            ret_data = {"status": "success", "return": "Successfully stopped worker."}
        except (WorkerNotFoundError, GenericException, WorkerMethodCallError) as e:
            ret_data = {"status": "error", "return": e.serialize()}
        return ret_data

    @BlockingEndpoint("close_worker")
    @Respond("close_worker")
    def __remote_close_worker__(self, rid: str, data: dict):
        try:
            self.close_worker(data["identifier"])
            ret_data = {"status": "success", "return": "Successfully closed worker."}
        except (WorkerNotFoundError, GenericException, WorkerMethodCallError) as e:
            ret_data = {"status": "error", "return": e.serialize()}
        return ret_data

    @BlockingEndpoint("close_process")
    def __remote_close_process__(self, rid: str, data: dict):
        self.__close_process__(rid)

    @BlockingEndpoint("add_component")
    @Respond("add_component")
    def __remote_add_component__(self, rid: str, data: dict):
        try:
            self.add_component(data["name"], data["import_path"], data["config"])
            ret_data = {"status": "success", "return": "Successfully added component."}
        except (KxProcessComponentImportError, KxProcessComponentInitError) as e:
            ret_data = {"status": "error", "return": e.serialize()}
        return ret_data


def __launch__(identifier: str, auth_key: str, host: str = "localhost", port: int = 6969,
               artificial_latency: float = 0.1):
    # IN A SUBPROCESS
    try:
        # Create process
        process = KxProcess(identifier, auth_key, host, port, artificial_latency)
    except SocketClientConnectionError as e:
        e.add_ctx(f"KxProcess '{identifier}' launch: error while creating the KxProcess.")
        LOGGER.error_exception(e, CORE)
