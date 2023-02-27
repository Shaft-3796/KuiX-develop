name, import_path = "BaseStrategy", "src.strategies.BaseStrategy"
module = __import__(import_path, fromlist=[name])
imp = getattr(module, name)
print(type(imp))