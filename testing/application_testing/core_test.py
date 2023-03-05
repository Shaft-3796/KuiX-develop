import time

from src.core.core import KuiX
from src.core.Logger import LOGGER

LOGGER.enable_verbose()


core = KuiX()
# core.generate_json_config()
core.load_json_config()
core.start()


core.create_process("KXP 1")
while "KXP 1" not in core.kx_processes:
    time.sleep(0.1)
core.register_strategy("DebugStrategy", "/media/x/Projects/Dev Python/KuiX/src/strategies/BaseStrategy.py")
core.create_worker("KXP 1", "DebugStrategy", "WORKER 1")
core.start_worker("KXP 1", "WORKER 1")
time.sleep(5)
time.sleep(2)
print("Stopping worker 1...")
core.stop_worker("KXP 1", "WORKER 1")
time.sleep(2)
print("destroying worker 1...")
core.close_worker("KXP 1", "WORKER 1")
