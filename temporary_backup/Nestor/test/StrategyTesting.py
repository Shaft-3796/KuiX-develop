import time

from src.strategies.BaseStrategy import BaseStrategy, StrategyStatus
from src.strategies.DebugStrategy import DebugStrategy

strategy = DebugStrategy("test")
strategy.start()
time.sleep(10)
strategy.stop()