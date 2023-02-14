import time

from src.strategies.BaseStrategy import DebugStrategy

strat = DebugStrategy("test")
strat.start()
time.sleep(5)
strat.stop()