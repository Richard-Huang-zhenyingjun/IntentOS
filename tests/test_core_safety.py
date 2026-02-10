"""Core safety tests - false_executions == 0."""

import pytest
import yaml
import sys
from pathlib import Path

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.system_factory import build_system


def test_false_executions_zero():
    """CRITICAL: false_executions must always be 0."""
    # Load config
    with open('configs/default.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Build with current composition root and force headless sim.
    config.setdefault('simulator', {})
    config['simulator']['use_gui'] = False
    orch = build_system(config)
    try:
        # Run many steps
        for _ in range(100):
            snapshot = orch.step()
        
        # CRITICAL CHECK
        assert snapshot.false_executions == 0, \
            f"CRITICAL: false_executions = {snapshot.false_executions} (must be 0)"
    finally:
        orch.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
