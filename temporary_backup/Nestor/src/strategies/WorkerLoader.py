class WorkerLoader:

    def __init__(self, identifier: str, *args, **kwargs):
        self.identifier = identifier
        self.args = args
        self.kwargs = kwargs
