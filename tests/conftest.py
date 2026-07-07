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

# pybullet has no prebuilt wheel for this Python/platform combo and fails to
# build from source here. It's only needed transitively (src.robot.simulator
# imports it at module level), so most tests never touch real physics and
# only need the import to resolve. Stub it before any src import so the full
# suite can collect. Tests that actually instantiate RobotSimulator (real
# physics, not this stub) will still fail loudly against these mocks - that's
# intentional, see HANDOFF/session notes: those need real pybullet installed,
# not a smarter mock.
for _name in ("pybullet", "pybullet_data"):
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()


