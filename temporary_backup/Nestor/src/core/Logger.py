import time
from dataclasses import dataclass
from .Exception import NestorException


@dataclass
class C:
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    GRAY = '\033[37m'

    BBLACK = '\033[40m'
    BRED = '\033[41m'
    BGREEN = '\033[42m'
    BYELLOW = '\033[43m'
    BBLUE = '\033[44m'
    BMAGENTA = '\033[45m'
    BCYAN = '\033[46m'
    BGRAY = '\033[47m'

    END = '\033[0m'
    BOLD = '\033[1m'
    ITALIC = '\033[3m'


class LogTypes:
    INFO = f"{C.BOLD}{C.BGREEN}{C.BLACK}$TIME $ROUTE INFO:{C.END}{C.GREEN} $DATA{C.END}"
    WARNING = f"{C.BOLD}{C.BYELLOW}{C.BLACK}$TIME $ROUTE WARNING:{C.END}{C.YELLOW} $DATA{C.END}"
    ERROR = f"{C.BOLD}{C.BRED}{C.BLACK}$TIME $ROUTE ERROR:{C.END}{C.RED} $DATA{C.END}"
    DEBUG = f"{C.BOLD}{C.BCYAN}{C.BLACK}$TIME $ROUTE DEBUG:{C.END}{C.MAGENTA} $DATA{C.END}"


def log(log_type: str, message):
    _log = log_type.replace("$TIME", time.strftime("%d-%m-%y %H:%M:%S")).replace("$DATA", message)
    print(_log)
    # TODO: Add potential log file


def log_exception(exception: NestorException):
    data = f"{C.BOLD}{C.BRED}{C.BLACK}{time.strftime('%d-%m-%y %H:%M:%S')} ERROR:{C.END}{C.RED} " \
           f"Msg traceback: {'->'.join(exception.messages_traceback)}" \
           f"\nTraceback: {C.ITALIC}{exception.traceback}{C.END}"
    print(data)


def dump_exception(exception: Exception, message: str = None):
    if type(exception) == NestorException:
        exception.add_traceback(message)
    exception = NestorException(exception, message)
    log_exception(exception)
