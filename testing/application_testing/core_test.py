import time

from src.core.core import KuiX
from src.core.Logger import LOGGER

LOGGER.enable_verbose()

core = KuiX()
core.load_json_config()
core.startup()
core.create_process("KXP 1")
time.sleep(1)
core.register_strategy("BaseStrategy", "src.strategies.BaseStrategy")
core.create_worker("KXP 1", "BaseStrategy", "WORKER 1")