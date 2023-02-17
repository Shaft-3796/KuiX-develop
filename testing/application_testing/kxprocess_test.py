from src.core.Logger import LOGGER, CORE
from src.core.process.kxprocess import launch

try:
    launch("CLI1", "test", "172.0.0.1", 60000, 0.1)
except BaseException as e:
    LOGGER.error_exception(e, CORE)
