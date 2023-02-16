import threading
import time
import socket

from src.core.Exceptions import GenericException, cast
from src.core.Logger import LOGGER

try:
    try:
        try:
            8/0
        except BaseException as e:
            e = cast(e)
            e.add_note("Exception raised in lvl 0")
            raise e
    except BaseException as e:
        e = cast(e)
        e.add_note("Exception raised in lvl 1")
        raise e
except BaseException as e:
    e = cast(e)
    e.add_note("Exception raised in lvl 2")
    LOGGER.warning_exception(e, "CORE")


