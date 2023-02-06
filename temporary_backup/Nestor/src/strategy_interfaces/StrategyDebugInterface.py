from .BaseInterface import BaseInterface
from src.core.Logger import log, LogTypes


class StrategyDebugInterface(BaseInterface):

    def __init__(self):
        super().__init__()

    # Override, called before a strategy is started
    def start(self, *args, **kwargs):
        log(LogTypes.INFO, "[DebugInterface] Started")

    # Override, called after a strategy is stopped
    def stop(self, *args, **kwargs):
        log(LogTypes.INFO, "[DebugInterface] Stopped")

    # New methods
    def buy(self, *args, **kwargs):
        log(LogTypes.INFO, "[DebugInterface] Bought")

    def sell(self, *args, **kwargs):
        log(LogTypes.INFO, "[DebugInterface] Sold")
