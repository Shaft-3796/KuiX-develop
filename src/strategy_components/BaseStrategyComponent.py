"""
Implements the base strategy component class.
There is also an implementation of a debug strategy component.
"""
from src.core.Logger import LOGGER, STRATEGY_COMP

# TODO: document all methods of this class

class BaseStrategyComponent:

    # Constructor for the component
    def __init__(self, worker):
        self.worker = worker

    # To override, called to start the component
    def start_component(self):
        pass

    # To override, called to stop the component
    def stop(self):
        pass

    # To override, called to destruct the component
    def destruct(self):
        pass


class DebugStrategyComponent(BaseStrategyComponent):

    # Constructor for the component
    def __init__(self, worker):
        super().__init__(worker)

    # To override, called to start the component
    def start_component(self):
        LOGGER.info(f"DebugStrategyComponent for worker {self.worker.identifier} started.", STRATEGY_COMP)

    # To override, called to stop the component
    def stop(self):
        LOGGER.info(f"DebugStrategyComponent for worker {self.worker.identifier} stopped.", STRATEGY_COMP)

    # To override, called to destruct the component
    def destruct(self):
        LOGGER.info(f"DebugStrategyComponent for worker {self.worker.identifier} destructed.", STRATEGY_COMP)

    # A debug call
    def debug_call(self):
        LOGGER.info(f"DebugStrategyComponent for worker {self.worker.identifier} debug call.", STRATEGY_COMP)
