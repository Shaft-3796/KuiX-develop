from src.core.Nestor import Nestor
from src.strategies.BaseStrategy import BaseStrategy, StrategyStatus
from src.strategies.DebugStrategy import DebugStrategy
from src.strategies.WorkerLoader import WorkerLoader

nestor = Nestor()

nestor.configure_from_file()
nestor.add_strategy(DebugStrategy)

# Create a worker
loader = WorkerLoader("test")
nestor.create_worker("DebugStrategy", loader)
