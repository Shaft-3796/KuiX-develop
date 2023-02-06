class BaseInterface:

    def __init__(self, *args, **kwargs):
        self._strategy = None

    # To override, called before a strategy is started
    def start(self, *args, **kwargs):
        pass

    # To override, called after a strategy is stopped
    def stop(self, *args, **kwargs):
        pass
