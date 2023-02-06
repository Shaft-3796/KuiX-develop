# This file implements the BasStrategy class, which is the base class for all strategies.
import dataclasses
import threading
import time


@dataclasses.dataclass
class StrategyStatus:
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class BaseStrategy:
    NAME = "BaseStrategy"

    def __init__(self, identifier: str):
        self.identifier = identifier
        self.thread = None
        self.status = StrategyStatus.STOPPED
        self.interfaces = {}

    # --- Thread Related ---

    # Override not recommended, Start a strategy
    def start(self):
        if self.thread is not None:
            return 1
        # Starting interfaces
        for interface in self.interfaces.values():
            interface.start()
        # Starting strategy
        self.thread = threading.Thread(target=self.strategy, name=f"STRATEGY_{self.NAME}_{self.identifier}")
        self.status = StrategyStatus.STARTING
        self.thread.start()
        self.status = StrategyStatus.RUNNING
        return 0

    # Override not recommended, Schedule a stop
    def stop(self):
        self.status = StrategyStatus.STOPPING
        self.thread = None

    # Override not recommended, called by the strategy to check if it should stop
    def check_for_stop(self, *args, **kwargs):
        if self.status == StrategyStatus.STOPPING:
            self.before_close(*args, **kwargs)
            # Stopping interfaces
            for interface in self.interfaces.values():
                interface.stop()
            self.status = StrategyStatus.STOPPED
            self.thread = None
            exit(0)  # Exit strategy thread

    # --- Strategy Related ---
    # To override, called to start the strategy
    def strategy(self, *args, **kwargs):
        while True:
            pass
            self.check_for_stop()
            time.sleep(1)

    # To override, used to do some stuff before the strategy is completely stopped
    def before_close(self, *args, **kwargs):
        pass
