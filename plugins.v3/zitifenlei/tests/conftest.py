import sys
import types
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

# 以「虚拟包」方式加载插件模块，避免执行插件 __init__.py（依赖 MoviePilot 宿主 SDK）
PACKAGE_NAME = "ziti_under_test"
if PACKAGE_NAME not in sys.modules:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(PLUGIN_ROOT)]
    sys.modules[PACKAGE_NAME] = package
