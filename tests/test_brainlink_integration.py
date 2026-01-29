"""
Integration tests for BrainLink EEG system.
Week 7: End-to-end tests for BCI integration.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import pytest
import time
import yaml
from intent_core.arm_intent_schema import DecisionSignal
from input.brainlink import BrainLinkDecisionSource
from input import MockEEG


@pytest.fixture
def default_cfg():
    """Load default config."""
    cfg_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'robotics.yaml')
    with open(cfg_path, 'r') as f:
        return yaml.safe_load(f)


class TestMockEEGIntegration:
    """Test MockEEG integration (always available)."""
    
    def test_mock_eeg_lifecycle(self, default_cfg):
        """Test MockEEG start, close."""
        mock_eeg = MockEEG(mode="keyboard")
        
        # Start
        assert mock_eeg.start() == True
        assert mock_eeg.get_source_name() == "MockEEG (keyboard)"
        
        # Confidence (doesn't require reading)
        conf = mock_eeg.get_confidence()
        assert 0.0 <= conf <= 1.0
        
        # Close
        mock_eeg.close()
        
        # Note: Can't test read_signal() without PyBullet connection
    
    def test_mock_eeg_properties(self, default_cfg):
        """Test MockEEG properties."""
        mock_eeg = MockEEG(mode="keyboard")
        mock_eeg.start()
        
        # Check properties
        assert mock_eeg.get_source_name() == "MockEEG (keyboard)"
        assert mock_eeg.get_confidence() >= 0.9  # MockEEG always confident
        
        mock_eeg.close()


class TestBrainLinkIntegration:
    """Test BrainLink integration (may fallback if no hardware)."""
    
    def test_brainlink_lifecycle(self, default_cfg):
        """Test BrainLink start, read, close."""
        brainlink = BrainLinkDecisionSource(default_cfg)
        
        # Start (may fail if no hardware)
        started = brainlink.start()
        # Should return True or False, not crash
        assert isinstance(started, bool)
        
        # Read (should return IDLE if not started or no signal)
        signal = brainlink.read_signal()
        assert signal in [DecisionSignal.IDLE, DecisionSignal.CONFIRM, DecisionSignal.CANCEL]
        
        # Confidence
        conf = brainlink.get_confidence()
        assert 0.0 <= conf <= 1.0
        
        # Close
        brainlink.close()
    
    def test_brainlink_debug_status(self, default_cfg):
        """Test BrainLink debug status reporting."""
        brainlink = BrainLinkDecisionSource(default_cfg)
        brainlink.start()
        
        # Get debug status
        status = brainlink.get_debug_status()
        
        # Check required fields
        assert "connected" in status
        assert "stable" in status
        assert "blocked" in status
        assert "confidence" in status
        
        # If not connected, should report blocked
        if not status["connected"]:
            assert status["blocked"] == True
        
        brainlink.close()
    
    def test_brainlink_no_hardware_fallback(self, default_cfg):
        """Test that BrainLink handles no hardware gracefully."""
        brainlink = BrainLinkDecisionSource(default_cfg)
        
        # Try to start (likely no hardware)
        started = brainlink.start()
        
        # Should not crash regardless
        signal = brainlink.read_signal()
        assert signal == DecisionSignal.IDLE
        
        status = brainlink.get_debug_status()
        assert "connected" in status
        
        brainlink.close()
    
    def test_brainlink_stability_blocking(self, default_cfg):
        """Test that BrainLink blocks on unstable signal."""
        brainlink = BrainLinkDecisionSource(default_cfg)
        brainlink.start()
        
        # Read multiple times
        signals = []
        for _ in range(10):
            signal = brainlink.read_signal()
            signals.append(signal)
            time.sleep(0.05)
        
        # Should produce valid signals (IDLE if unstable/no hardware)
        for sig in signals:
            assert sig in [DecisionSignal.IDLE, DecisionSignal.CONFIRM, DecisionSignal.CANCEL]
        
        # Check debug status
        status = brainlink.get_debug_status()
        
        # If not connected, should be blocked
        if not status["connected"]:
            assert status["blocked"] == True
        
        brainlink.close()


class TestOrchestratorIntegration:
    """Test orchestrator with EEG sources."""
    
    def test_orchestrator_with_mock_eeg(self, default_cfg):
        """Test orchestrator initialization with MockEEG."""
        from intent_core import ArmOrchestrator
        
        orch = ArmOrchestrator(default_cfg, use_eeg=True, eeg_source="mock")
        
        # Should have decision source
        assert orch.decision_source is not None
        assert "MockEEG" in orch.decision_source.get_source_name()
        
        # Note: Can't test read_signal() without PyBullet
    
    def test_orchestrator_with_brainlink(self, default_cfg):
        """Test orchestrator initialization with BrainLink (fallback if no hardware)."""
        from intent_core import ArmOrchestrator
        
        orch = ArmOrchestrator(default_cfg, use_eeg=True, eeg_source="brainlink")
        
        # Should have decision source (BrainLink or fallback to MockEEG)
        assert orch.decision_source is not None
        
        # Note: Can't test read_signal() without PyBullet or hardware
    
    def test_orchestrator_keyboard_mode(self, default_cfg):
        """Test orchestrator in keyboard-only mode."""
        from intent_core import ArmOrchestrator
        
        orch = ArmOrchestrator(default_cfg, use_eeg=False)
        
        # Should have keyboard input, not EEG source
        assert orch.decision_source is None
        assert hasattr(orch, 'input')


class TestStateMachineEEGIntegration:
    """Test state machine with EEG stability gates."""
    
    def test_state_machine_stability_check(self, default_cfg):
        """Test state machine EEG stability checking."""
        from intent_core import ArmStateMachine
        
        sm = ArmStateMachine()
        
        # Test with no EEG (always stable)
        stable = sm.check_eeg_stability(None)
        assert stable == True
        
        # Test with stable EEG
        eeg_meta_stable = {
            "blocked": False,
            "stable": True
        }
        stable = sm.check_eeg_stability(eeg_meta_stable)
        assert stable == True
        
        # Test with unstable EEG
        eeg_meta_unstable = {
            "blocked": True,
            "stable": False,
            "reason": "High variance"
        }
        stable = sm.check_eeg_stability(eeg_meta_unstable)
        assert stable == False
        assert sm.eeg_unstable_frames > 0
    
    def test_state_machine_prolonged_instability(self, default_cfg):
        """Test that prolonged instability triggers PAUSED state."""
        from intent_core import ArmStateMachine, ArmUIState
        
        sm = ArmStateMachine()
        
        # Set to critical state (AWAITING_CONFIRM)
        sm.state = ArmUIState.AWAITING_CONFIRM
        sm.active_target_id = 1
        sm.target_locked = True
        
        # Simulate prolonged instability
        eeg_meta_unstable = {
            "blocked": True,
            "stable": False,
            "reason": "No signal"
        }
        
        # Trigger instability for max_unstable_frames + 1
        for _ in range(sm.max_unstable_frames + 1):
            sm.check_eeg_stability(eeg_meta_unstable)
        
        # Should transition to PAUSED
        assert sm.state == ArmUIState.PAUSED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

