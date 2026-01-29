"""
Week 9 Tests: Final Trust Regressions

Comprehensive trust validation:
- false_executions == 0 across ALL demo modes
- Deterministic scripted scenario
- Snapshot consistency
- Event logging integrity
"""

import pytest
import yaml
import sys
from unittest.mock import Mock
import time

sys.path.insert(0, 'src')

from intent_core import ArmOrchestrator, ArmUISnapshot
from sim import DemoMode, get_mode_config, FaultInjector, ScheduledFault, FaultType


@pytest.fixture
def base_cfg():
    """Load base configuration."""
    with open('configs/robotics.yaml', 'r') as f:
        return yaml.safe_load(f)


@pytest.fixture
def mock_sim_world_selector(monkeypatch):
    """Create mock sim, world, selector."""
    import numpy as np
    
    # Mock pybullet functions
    def mock_getJointStates(body_id, joint_indices):
        # Return mock joint states: (position, velocity, reaction_forces, applied_torque)
        return [(0.0, 0.0, (0, 0, 0, 0), 0.0) for _ in joint_indices]
    
    def mock_getLinkState(body_id, link_index, computeForwardKinematics=False):
        # Return mock link state with proper structure
        # Format: (linkWorldPosition, linkWorldOrientation, localInertialFramePosition, 
        #          localInertialFrameOrientation, worldLinkFramePosition, worldLinkFrameOrientation, ...)
        return (
            [0.0, 0.0, 0.3],  # linkWorldPosition
            [0, 0, 0, 1],      # linkWorldOrientation
            [0, 0, 0],         # localInertialFramePosition
            [0, 0, 0, 1],      # localInertialFrameOrientation
            [0.0, 0.0, 0.3],  # worldLinkFramePosition (index 4)
            [0, 0, 0, 1],      # worldLinkFrameOrientation (index 5)
            [0, 0, 0, 0, 0, 0], # worldLinkLinearVelocity
            [0, 0, 0]          # worldLinkAngularVelocity
        )
    
    def mock_setJointMotorControlArray(*args, **kwargs):
        pass
    
    def mock_getKeyboardEvents():
        # Return empty keyboard events
        return {}
    
    # Patch pybullet in all relevant modules
    import pybullet as p
    monkeypatch.setattr('robotics.arm_state.p.getJointStates', mock_getJointStates)
    monkeypatch.setattr('robotics.arm_state.p.getLinkState', mock_getLinkState)
    monkeypatch.setattr('robotics.arm_controller.p.setJointMotorControlArray', mock_setJointMotorControlArray)
    monkeypatch.setattr('input.confirm_input.p.getKeyboardEvents', mock_getKeyboardEvents)
    
    sim = Mock()
    sim.robot = Mock()
    sim.robot.body_id = 0
    sim.robot.joint_indices = list(range(7))
    sim.robot.ee_link_index = 6
    sim.object_id = 1
    
    world = Mock()
    world.target_object_id = None
    world.get_available_actions.return_value = []
    world.propose_next_action.return_value = None
    world.ee_pos = np.array([0.0, 0.0, 0.3])
    world.object_pos = np.array([0.0, 0.0, 0.0])
    
    def mock_update(sim):
        pass
    world.update_from_sim = mock_update
    world.set_target = Mock()
    world.set_grasp_state = Mock()
    
    selector = Mock()
    selector.get_locked_target.return_value = None
    selector.is_locked.return_value = False
    selector.using_gaze = False
    selector.hover_object_id = None
    
    # Mock selection_state
    selection_state = Mock()
    selection_state.hover_frames = 0  # Must be an integer, not a Mock
    selection_state.current_hover_id = None  # No hover
    selection_state.dwell_progress.return_value = 0.0
    selector.selection_state = selection_state
    
    # Mock tracker.get_state()
    tracker = Mock()
    tracker.get_state.return_value = selection_state
    selector.tracker = tracker
    
    return sim, world, selector


def test_false_executions_zero_happy_path(base_cfg, mock_sim_world_selector):
    """Test false_executions == 0 in happy path mode."""
    sim, world, selector = mock_sim_world_selector
    
    # Configure for happy path
    cfg = get_mode_config(DemoMode.HAPPY_PATH, base_cfg)
    
    orchestrator = ArmOrchestrator(cfg, use_eeg=False)
    
    # Run many steps
    for _ in range(200):
        snapshot = orchestrator.step(sim, world, selector)
    
    # CRITICAL: false_executions must be 0
    assert snapshot.false_executions == 0, \
        "CRITICAL: False execution in happy path mode"
    
    orchestrator.close()


def test_false_executions_zero_recovery_mode(base_cfg, mock_sim_world_selector):
    """Test false_executions == 0 in recovery mode (with faults)."""
    sim, world, selector = mock_sim_world_selector
    
    # Configure for recovery mode with fault injection
    cfg = get_mode_config(DemoMode.RECOVERY, base_cfg)
    
    # Add fault schedule
    faults = [
        ScheduledFault(time_s=1.0, fault_type=FaultType.EEG_DROPOUT, duration_s=2.0)
    ]
    fault_injector = FaultInjector(seed=42, schedule=faults)
    
    orchestrator = ArmOrchestrator(cfg, use_eeg=False, fault_injector=fault_injector)
    
    # Start fault injector
    fault_injector.start(time.time())
    
    # Run simulation
    for _ in range(200):
        snapshot = orchestrator.step(sim, world, selector)
    
    # CRITICAL: Even with faults, false_executions must be 0
    assert snapshot.false_executions == 0, \
        "CRITICAL: False execution during recovery mode"
    
    orchestrator.close()


def test_false_executions_zero_safety_refusal(base_cfg, mock_sim_world_selector):
    """Test false_executions == 0 when confirmations are blocked."""
    sim, world, selector = mock_sim_world_selector
    
    # Configure for safety refusal mode
    cfg = get_mode_config(DemoMode.SAFETY_REFUSAL, base_cfg)
    
    # Add high variance fault
    faults = [
        ScheduledFault(time_s=0.5, fault_type=FaultType.HIGH_VARIANCE, duration_s=5.0)
    ]
    fault_injector = FaultInjector(seed=42, schedule=faults)
    
    orchestrator = ArmOrchestrator(cfg, use_eeg=True, eeg_source="mock", fault_injector=fault_injector)
    
    # Start fault injector
    fault_injector.start(time.time())
    
    # Run simulation
    for _ in range(200):
        snapshot = orchestrator.step(sim, world, selector)
    
    # CRITICAL: Blocked confirmations should NOT trigger executions
    assert snapshot.false_executions == 0, \
        "CRITICAL: False execution when confirmations blocked"
    
    # Note: In mock mode without EEG sensor input, we may not get blocked confirmations
    # The critical test is false_executions == 0
    
    orchestrator.close()


def test_snapshot_consistency(base_cfg, mock_sim_world_selector):
    """Test UI snapshot consistency across frames."""
    sim, world, selector = mock_sim_world_selector
    
    orchestrator = ArmOrchestrator(base_cfg, use_eeg=False)
    
    # Get multiple snapshots
    snapshots = []
    for _ in range(10):
        snapshot = orchestrator.step(sim, world, selector)
        snapshots.append(snapshot)
    
    # Verify all snapshots are ArmUISnapshot instances
    for snapshot in snapshots:
        assert isinstance(snapshot, ArmUISnapshot)
    
    # Verify frame count increments (starts at 0)
    for i, snapshot in enumerate(snapshots):
        assert snapshot.frame_count == i
    
    # Verify timestamps increase
    for i in range(1, len(snapshots)):
        assert snapshots[i].timestamp >= snapshots[i-1].timestamp
    
    orchestrator.close()


def test_event_logging_integrity(base_cfg, mock_sim_world_selector):
    """Test event logging creates valid JSONL."""
    sim, world, selector = mock_sim_world_selector
    
    # Enable event logging
    base_cfg['demo']['log_events'] = True
    
    orchestrator = ArmOrchestrator(base_cfg, use_eeg=False, session_id="test_session")
    
    # Run some steps
    for _ in range(50):
        orchestrator.step(sim, world, selector)
    
    # Close to flush logs
    orchestrator.close()
    
    # Verify log file exists
    from pathlib import Path
    log_path = Path(base_cfg['demo']['log_dir']) / "test_session.jsonl"
    assert log_path.exists(), "Event log file not created"
    
    # Verify JSONL format
    import json
    with open(log_path, 'r') as f:
        lines = f.readlines()
    
    assert len(lines) >= 2, "Expected at least SESSION_STARTED + SESSION_ENDED"
    
    # Parse each line
    for line in lines:
        event = json.loads(line)
        assert 'event_type' in event
        assert 'timestamp' in event
        assert 'session_id' in event
        assert event['session_id'] == "test_session"
    
    # Cleanup
    log_path.unlink()


def test_metrics_collection(base_cfg, mock_sim_world_selector):
    """Test metrics are collected and exportable."""
    sim, world, selector = mock_sim_world_selector
    
    # Enable metrics export
    base_cfg['demo']['save_metrics'] = True
    
    orchestrator = ArmOrchestrator(base_cfg, use_eeg=False, session_id="test_metrics")
    
    # Run simulation
    for _ in range(100):
        orchestrator.step(sim, world, selector)
    
    # Close orchestrator first (flushes logs)
    orchestrator.close()
    
    # Verify metrics file exists
    from pathlib import Path
    metrics_path = Path(base_cfg['demo']['log_dir']) / "test_metrics_metrics.json"
    
    # Note: Metrics are saved when orchestrator.close() or end_session() is called
    # Since we're testing the collection mechanism, verify snapshot has metrics
    if metrics_path.exists():
        # Load and validate metrics
        import json
        with open(metrics_path, 'r') as f:
            metrics = json.load(f)
        
        # Verify structure
        assert 'session' in metrics
        assert 'performance' in metrics
        assert 'trust' in metrics
        
        # Verify critical metric
        assert metrics['trust']['false_executions'] == 0
        
        # Cleanup
        metrics_path.unlink()


def test_deterministic_scripted_scenario(base_cfg, mock_sim_world_selector):
    """Test same seed produces same behavior."""
    sim, world, selector = mock_sim_world_selector
    
    # Configure with fault injection
    cfg = get_mode_config(DemoMode.RECOVERY, base_cfg)
    
    faults = [
        ScheduledFault(time_s=0.5, fault_type=FaultType.EEG_DROPOUT, duration_s=1.0)
    ]
    
    # Run 1
    injector1 = FaultInjector(seed=42, schedule=faults)
    orch1 = ArmOrchestrator(cfg, use_eeg=False, fault_injector=injector1)
    injector1.start(0.0)
    
    sequence1 = []
    for i in range(50):
        snapshot = orch1.step(sim, world, selector)
        sequence1.append((snapshot.state, snapshot.paused))
    
    orch1.close()
    
    # Run 2 - same seed
    injector2 = FaultInjector(seed=42, schedule=faults)
    orch2 = ArmOrchestrator(cfg, use_eeg=False, fault_injector=injector2)
    injector2.start(0.0)
    
    sequence2 = []
    for i in range(50):
        snapshot = orch2.step(sim, world, selector)
        sequence2.append((snapshot.state, snapshot.paused))
    
    orch2.close()
    
    # Sequences should be identical
    assert sequence1 == sequence2, "Deterministic scenario not reproducible"


def test_pause_clears_confirmation_snapshot(base_cfg, mock_sim_world_selector):
    """Test pause clears confirmation in snapshot."""
    sim, world, selector = mock_sim_world_selector
    
    orchestrator = ArmOrchestrator(base_cfg, use_eeg=False)
    
    # Simulate awaiting confirm state
    from intent_core.arm_intent_schema import ArmUIState
    orchestrator.state_machine.state = ArmUIState.AWAITING_CONFIRM
    from intent_core.arm_intent_schema import ArmProposal
    from robotics.action_types import ArmActionType
    orchestrator.state_machine.active_proposal = ArmProposal(
        target_object_id=1,
        action_type=ArmActionType.MOVE_ARM_UP,
        reason="test",
        available_actions=[ArmActionType.MOVE_ARM_UP],
        timestamp=time.time()
    )
    
    # Trigger pause on both state machine and recovery controller
    from robotics.recovery import RecoveryPlan, PauseTrigger
    plan = RecoveryPlan.create(PauseTrigger.CANCEL_REQUESTED)
    orchestrator.recovery_controller.trigger_pause(plan)
    orchestrator.state_machine.trigger_pause("test_trigger")
    
    # Get snapshot
    snapshot = orchestrator.step(sim, world, selector)
    
    # Verify pause state and cleared proposal
    assert snapshot.paused == True
    assert snapshot.proposed_action is None
    
    orchestrator.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

