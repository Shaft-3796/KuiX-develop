"""
This file handle logging and exception handling
"""
from ..Utils import C, KXTException
from dataclasses import dataclass
import multiprocessing
import json
import time
import os


# --- Log types and data ---
INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"
DEBUG = "DEBUG"


@dataclass
class LogTypes:
    __type_header_color__ = {INFO: f"{C.BOLD}{C.BGREEN}{C.BLACK}", WARNING: f"{C.BOLD}{C.BYELLOW}{C.BLACK}",
                             ERROR: f"{C.BOLD}{C.BRED}{C.BLACK}", DEBUG: f"{C.BOLD}{C.BCYAN}{C.BLACK}"}
    __type_body_color__ = {INFO: f"{C.END}{C.GREEN}", WARNING: f"{C.END}{C.YELLOW}", ERROR: f"{C.END}{C.RED}",
                           DEBUG: f"{C.END}{C.MAGENTA}"}


# -- Logging routes --
CORE = "CORE"
CORE_COMP = "CORE_COMPONENT"
STRATEGY = "STRATEGY"
STRATEGY_COMP = "STRATEGY_COMPONENT"


# LOGGER
class Logger:

    def __init__(self):
        # PLACEHOLDER
        self.log_path = None
        self.lock = multiprocessing.Lock()

    # Call to enable file logging
    def set_log_path(self, path: str):
        try:
            self.log_path = path
            # Create log files
            os.makedirs(self.log_path, exist_ok=True)
            # Create log files for each route
            for route in [CORE, CORE_COMP, STRATEGY, STRATEGY_COMP]:
                for log_type in [INFO, WARNING, ERROR, DEBUG]:
                    if not os.path.exists(f"{self.log_path}/{route}_{log_type}.log"):
                        open(f"{self.log_path}/{route}_{log_type}.log", "w").close()
        except Exception as e:
            print("KXT Error: Logger could not be initialized, exiting...")
            raise e

    # --- Core ---
    def log(self, data: str, log_type: str, route: str):
        with self.lock:
            color_header = LogTypes.__type_header_color__[log_type]
            color_body = LogTypes.__type_body_color__[log_type]
            log_time = time.strftime("%d-%m-%y %H:%M:%S")

            # One line log
            _log = f"{color_header}{log_time}] [{log_type}] FROM [{route}]: {color_body}{data}{C.END}"

            # JSON log
            json_log = json.dumps({"time": log_time, "type": log_type, "route": route, "data": data})

            # Logging
            print(_log + '\n', end='')
            if self.log_path is not None:
                for retry in range(3):
                    try:
                        with open(f"{self.log_path}/{route}_{log_type}.log", "a") as f:
                            f.write(json_log + "\n")
                        break
                    except FileNotFoundError:
                        open(f"{self.log_path}/{route}_{log_type}.log", "w").close()

    def log_exception(self, exception: KXTException, route: str):
        self.log(f"KXT: {'->'.join(exception.messages_traceback)}"
                 f"\nException: {C.ITALIC}{exception.traceback}{C.END}", ERROR, route)

    def dump_exception(self, exception: Exception, route: str, message: str = None):
        if type(exception) == KXTException:
            exception.add_traceback(message)
        else:
            exception = KXTException(exception, message)
        self.log_exception(exception, route)

    # --- SHORTCUTS ---
    def info(self, data: str, route: str):
        self.log(data, INFO, route)

    def warning(self, data: str, route: str):
        self.log(data, WARNING, route)

    def error(self, data: str, route: str):
        self.log(data, ERROR, route)

    def debug(self, data: str, route: str):
        self.log(data, DEBUG, route)


# Pre instanced logger
LOGGER = Logger()
