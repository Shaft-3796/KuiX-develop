"""
Implements the base strategy class.
There is also an implementation of a debug strategy.
"""
from abc import abstractmethod

from src.core.Exceptions import *
from src.strategy_components.BaseStrategyComponent import DebugStrategyComponent, BaseStrategyComponent
from src.core.Logger import LOGGER, STRATEGY
import dataclasses
import threading
import time


@dataclasses.dataclass
class StrategyStatus:
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


# TODO: document all methods of this class

class BaseStrategy:

    def __init__(self, identifier: str):
        # Args
        self.identifier = identifier

        self.thread = None  # Worker thread
        self.worker_status = StrategyStatus.STOPPED  # Worker status
        self.components = {}  # All strategy components

    def add_component(self, name, component):
        if not isinstance(component, BaseStrategyComponent):
            LOGGER.warning(
                f"Worker {self.identifier} of strategy {self.__class__} tried to add a component that is not "
                f"an instance of BaseStrategyComponent. This can lead to unexpected behaviours, inheritance "
                f"from BaseStrategyComponent is recommended.")
        self.components[name] = component
        return component

    # --- Core ---
    def __open__(self):
        for component in self.components.values():
            try:
                component.__open__()
            except Exception as e:
                raise StrategyComponentOpeningError(f"Error while opening strategy component: {component.__class__}, "
                                                    f"look at the initial exception for more details.") + e

    def __start__(self):
        # Checking if the worker is already started
        if self.thread is not None:
            raise WorkerAlreadyStarted("Worker is already started or still running.")
        # Starting components
        for component in self.components.values():
            try:
                component.__start__()
            except Exception as e:
                raise StrategyComponentStartingError(f"Error while starting strategy component: {component.__class__}, "
                                                     f"look at the initial exception for more details.") + e
        # Starting the worker
        self.thread = threading.Thread(target=self.strategy, name=f"STRATEGY_{self.__class__}_{self.identifier}")
        self.worker_status = StrategyStatus.STARTING
        self.thread.start()
        self.worker_status = StrategyStatus.RUNNING

    def __stop__(self):
        # Checking if the worker is already stopped
        if self.thread is None:
            raise WorkerAlreadyStopped("Worker is already stopped.")
        # Stopping the worker
        self.worker_status = StrategyStatus.STOPPING
        timer = 0
        _ = False
        while self.worker_status != StrategyStatus.STOPPED:
            if timer > 600:
                self.thread = None
                raise WorkerStoppingTimeout("Worker was scheduled to stop but is still running after 10mn. "
                                            "The strategy thread will be dumped but will be still running ! "
                                            "This will leads to unexpected behaviours and performances "
                                            "issues. Please consider adding self.check_status calls "
                                            "in your strategy.")
            if timer > 60 and not _:
                LOGGER.warning(f"Worker {self.identifier} was scheduled to stop but is still running after 60 seconds. "
                               f"Consider adding self.check_status calls in your strategy.", STRATEGY)
                _ = True
            time.sleep(0.1)
            timer += 0.1
        self.thread = None
        # Stopping components
        for component in self.components.values():
            try:
                component.__stop__()
            except Exception as e:
                raise StrategyComponentStoppingError(f"Error while stopping strategy component: {component.__class__}, "
                                                     f"look at the initial exception for more details.") + e

    def __close__(self):
        # Stop the worker
        try:
            self.__stop__()
        except WorkerAlreadyStopped:
            pass
        except WorkerStoppingTimeout as e:
            LOGGER.warning_exception(e, STRATEGY)
        except Exception as e:
            raise WorkerStoppingError(f"Error while stopping worker: {self.__class__}, "
                                      f"look at the initial exception for more details.") + e

        # Closing the strategy
        try:
            self.close_strategy()
        except Exception as e:
            raise StrategyClosingError(f"Error while closing strategy: {self.__class__}, "
                                       f"look at the initial exception for more details.") + e

        # Closing components
        for component in self.components.values():
            try:
                component.__close__()
            except Exception as e:
                raise StrategyComponentClosingError(f"Error while closing strategy component: {component.__class__}, "
                                                    f"look at the initial exception for more details.") + e

    def check_status(self):
        if self.worker_status == StrategyStatus.STOPPING:
            self.stop_strategy()
            self.worker_status = StrategyStatus.STOPPED
            exit(0)  # Exit strategy thread

    # --- Strategy ---
    def strategy(self):
        while True:
            pass
            self.check_status()
            time.sleep(1)

    def stop_strategy(self):
        pass

    def close_strategy(self):
        pass


class DebugStrategy(BaseStrategy):

    # Constructor for the strategy
    def __init__(self, identifier: str):
        super().__init__(identifier)

        # Add a component
        self.add_component("debug", DebugStrategyComponent(self))
        # Shortcuts
        self.debug = self.components["debug"]

    # The strategy
    def strategy(self):
        while True:
            self.check_status()
            LOGGER.info(f"DebugStrategy {self.identifier} running.", STRATEGY)
            self.debug.debug_call()
            time.sleep(1)

    def stop_strategy(self):
        LOGGER.info(f"DebugStrategy {self.identifier} stopping.", STRATEGY)

    def close_strategy(self):
        LOGGER.info(f"DebugStrategy {self.identifier} closing.", STRATEGY)
