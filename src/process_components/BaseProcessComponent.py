"""
Implements the base strategy component class.
There is also an implementation of a debug strategy component.
"""
from src.core.Logger import LOGGER, KX_PROCESS_COMP
from src.core.Utils import Respond
from src.core.process.KxProcess import KxProcess


class BaseProcessComponent:

    # Constructor of the component
    def __init__(self, kx_process: KxProcess):
        """
        Instance, this method is called by the KxProcess
        :param kx_process: The KxProcess instance
        """
        self.kx_process = kx_process

    # --- Core ---
    def __open__(self):
        """
        To override, called only once to open the component.
        """
        pass

    def __start__(self):
        """
        To override, called to start the component.
        """
        pass

    def __stop__(self):
        """
        To override, called to stop the component.
        """
        pass

    def __close__(self):
        """
        To override, called only once to close the component.
        """
        pass


class DebugProcessComponent(BaseProcessComponent):

    # Constructor for the component
    def __init__(self, kx_process: KxProcess):
        super().__init__(kx_process)

    def __open__(self):
        LOGGER.info(f"DebugProcessComponent for process {self.kx_process.identifier} opened.", KX_PROCESS_COMP)

        # We register a blocking endpoint to print something from the process
        @Respond("debug_call")
        def callback(rid, data):
            LOGGER.info(f"DebugProcessComponent for process {self.kx_process.identifier} debug call.", KX_PROCESS_COMP)
            return {"status": "success", "return": "Debug call success !"}

        self.kx_process.register_blocking_endpoint("debug_call", callback)

    def __start__(self):
        LOGGER.info(f"DebugProcessComponent for process {self.kx_process.identifier} started.", KX_PROCESS_COMP)

    def __stop__(self):
        LOGGER.info(f"DebugProcessComponent for process {self.kx_process.identifier} stopped.", KX_PROCESS_COMP)

    def __close__(self):
        LOGGER.info(f"DebugProcessComponent for process {self.kx_process.identifier} closed.", KX_PROCESS_COMP)

    # A debug call
    def debug_call(self):
        LOGGER.info(f"DebugProcessComponent for process {self.kx_process.identifier} debug call.", KX_PROCESS_COMP)
