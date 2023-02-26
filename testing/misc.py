import traceback

class customException(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

try:
    try:
        try:
            raise ValueError("Err")
        except ValueError as e:
            raise e
    except ValueError as e:
        raise customException("Err2") from e
except customException as e:
    print(traceback.format_tb(e.__traceback__))