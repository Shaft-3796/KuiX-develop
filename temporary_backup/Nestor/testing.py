from src2.core.Logger import *

logger = Logger()
logger.set_log_path("logs")


def logloop(pid):
    while True:
        logger.log(f"{pid}", INFO, CORE)


if __name__ == "__main__":
    for i in range(10):
        multiprocessing.Process(target=logloop, args=(i,)).start()
