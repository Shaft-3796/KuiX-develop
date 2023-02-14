"""
Implements the base strategy class.
There is also an implementation of a debug strategy.
"""

from src.strategy_components.BaseStrategyComponent import DebugStrategyComponent
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

        self.thread = None
        self.worker_status = StrategyStatus.STOPPED
        self.strategy_components = {}

    # Override not recommended, Start a strategy
    def start(self):
        if self.thread is not None:
            return 1
        # Starting components
        for component in self.strategy_components.values():
            component.start_component()
        # Starting strategy
        self.thread = threading.Thread(target=self.strategy, name=f"STRATEGY_{self.__class__}_{self.identifier}")
        self.worker_status = StrategyStatus.STARTING
        self.thread.start()
        self.worker_status = StrategyStatus.RUNNING
        return 0

    # Override not recommended, Schedule a stop
    def stop(self):
        self.worker_status = StrategyStatus.STOPPING

    # Override not recommended, Schedule and wait for a stop
    def blocking_stop(self):
        self.stop()
        while self.worker_status != StrategyStatus.STOPPED:
            time.sleep(0.1)

    # Override not recommended, Clear the worker to destruct it.
    def destruct(self):
        self.blocking_stop()
        for component in self.strategy_components.values():
            component.destruct()
        self.strategy_finish()

    # --- Strategy Related ---
    # To override, called to start the strategy
    def strategy(self):
        while True:
            pass
            self.strategy_check_status()
            time.sleep(1)

    # Override not recommended, called by the strategy to check if it should stop
    def strategy_check_status(self):
        if self.worker_status == StrategyStatus.STOPPING:
            self.strategy_stop()
            # Stopping components
            for component in self.strategy_components.values():
                component.stop()
            self.worker_status = StrategyStatus.STOPPED
            self.thread = None
            exit(0)  # Exit strategy thread

    # To override, do some stuff before the worker is stopped
    def strategy_stop(self):
        pass

    # To override, do some stuff before the worker is completely stopped
    def strategy_finish(self):
        pass


class DebugStrategy(BaseStrategy):

    # Constructor for the strategy
    def __init__(self, identifier: str):
        super().__init__(identifier)

        # Add a component
        self.strategy_components["debug"] = DebugStrategyComponent(self)
        # Shortcuts
        self.debug = self.strategy_components["debug"]

    # Called to start the strategy
    def strategy(self):
        while True:
            self.strategy_check_status()
            LOGGER.info(f"DebugStrategy {self.identifier} running.", STRATEGY)
            self.debug.debug_call()
            time.sleep(1)

    # To override, do some stuff before the worker is stopped
    def strategy_stop(self):
        LOGGER.info(f"DebugStrategy {self.identifier} stopping.", STRATEGY)

    # To override, do some stuff before the worker is completely stopped
    def strategy_finish(self):
        LOGGER.info(f"DebugStrategy {self.identifier} finished.", STRATEGY)
