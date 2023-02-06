import time

from .BaseStrategy import BaseStrategy, StrategyStatus
from src.strategy_interfaces.StrategyDebugInterface import StrategyDebugInterface
from src.core.Logger import log, LogTypes


class DebugStrategy(BaseStrategy):
    NAME = "DebugStrategy"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add Debug interface
        self.interfaces['debug'] = StrategyDebugInterface()

    def strategy(self):
        iterations = 0
        while True:
            log(LogTypes.INFO, f"[DebugStrategy] Iteration number {iterations}")
            self.check_for_stop(iterations)
            if iterations % 5 == 0 and iterations % 10 != 0:
                self.interfaces['debug'].buy()
            if iterations % 10 == 0:
                self.interfaces['debug'].sell()
            iterations += 1
            time.sleep(1)

    def before_close(self, iterations, *args, **kwargs):
        log(LogTypes.INFO, f"[DebugStrategy] Closed after {iterations} iterations")
