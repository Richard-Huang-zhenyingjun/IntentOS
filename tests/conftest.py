"""
Pytest configuration for all tests.
Adds project root to Python path so imports work correctly.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Add project root to Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# pybullet has no prebuilt wheel for some local dev setups (e.g. macOS arm64
# + Python 3.13) and fails to build from source there. It's only needed
# transitively (src.robot.simulator imports it at module level), so most
# tests never touch real physics and only need the import to resolve.
# Try the real package FIRST - CI (Linux) installs a real prebuilt wheel and
# must use it, not a mock. Only fall back to a stub if the real import fails,
# so tests that actually instantiate RobotSimulator get real physics wherever
# real pybullet is available, and merely fail to collect (not silently pass
# against fake data) wherever it isn't.
for _name in ("pybullet", "pybullet_data"):
    if _name not in sys.modules:
        try:
            __import__(_name)
        except ImportError:
            sys.modules[_name] = MagicMock()


