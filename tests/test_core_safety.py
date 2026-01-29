"""Core safety tests - false_executions == 0."""

import pytest
import yaml
import sys
from pathlib import Path

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.orchestrator import Orchestrator
from src.core.schema import DecisionSignal, ArmDecision
from src.input.decision_source import DecisionSource
from src.robot.simulator import RobotSimulator


class MockDecisionSource(DecisionSource):
    """Mock decision source for testing."""
    
    def __init__(self):
        self.signal = DecisionSignal.IDLE
    
    def read_decision(self) -> ArmDecision:
        import time
        return ArmDecision(
            signal=self.signal,
            confidence=1.0,
            source="mock",
            timestamp=time.time()
        )
    
    def get_source_name(self) -> str:
        return "Mock"
    
    def reset(self):
        self.signal = DecisionSignal.IDLE


def test_false_executions_zero():
    """CRITICAL: false_executions must always be 0."""
    # Load config
    with open('configs/default.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Create components
    sim = RobotSimulator(config, use_gui=False)
    decision_source = MockDecisionSource()
    orch = Orchestrator(config, decision_source, sim)
    
    # Run many steps
    for _ in range(100):
        snapshot = orch.step()
    
    # CRITICAL CHECK
    assert snapshot.false_executions == 0, \
        f"CRITICAL: false_executions = {snapshot.false_executions} (must be 0)"
    
    orch.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

