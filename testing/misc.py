import importlib.util
import sys
spec = importlib.util.spec_from_file_location("ExternalStrategy", "/media/x/Projects/Dev Python/KuiX/src/strategies/BaseStrategy.py")
foo = importlib.util.module_from_spec(spec)
sys.modules["ExternalStrategy"] = foo
spec.loader.exec_module(foo)
print(foo.BaseStrategy)
foo.BaseStrategy()