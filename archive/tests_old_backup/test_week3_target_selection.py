"""
Week 3 Tests: Target Selection + Dwell-to-Lock

Tests:
- Selection cursor creation
- Ray testing (synthetic)
- Dwell-to-lock logic
- Selection state transitions
"""

import pytest
import yaml
import sys

sys.path.insert(0, 'src')

from robotics import ArmSimulator
from perception import SelectionCursor, SelectionTracker, TargetSelector
from world import WorldModel


@pytest.fixture
def sim():
    """Create simulator in DIRECT mode."""
    with open('configs/robotics.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    cfg['scene']['use_gui'] = False
    
    with open('configs/robotics_test.yaml', 'w') as f:
        yaml.dump(cfg, f)
    
    sim = ArmSimulator(cfg_path='configs/robotics_test.yaml')
    sim.connect()
    sim.reset_world()
    
    yield sim
    
    sim.close()
    
    import os
    os.remove('configs/robotics_test.yaml')


def test_selection_cursor_creation():
    """Test SelectionCursor factory methods."""
    mouse_cursor = SelectionCursor.from_mouse(0.5, 0.5)
    assert mouse_cursor.source == "mouse"
    assert mouse_cursor.confidence == 1.0
    
    gaze_cursor = SelectionCursor.from_gaze(0.3, 0.7, 0.8)
    assert gaze_cursor.source == "gaze"
    assert gaze_cursor.confidence == 0.8


def test_selection_cursor_clamping():
    """Test cursor values are clamped to [0, 1]."""
    cursor = SelectionCursor.from_mouse(1.5, -0.5)
    assert cursor.u == 1.0
    assert cursor.v == 0.0


def test_selection_tracker_dwell_lock():
    """Test dwell-to-lock logic."""
    tracker = SelectionTracker(dwell_frames=5, unlock_grace_frames=3)
    
    # Hover same object for dwell_frames → should lock
    for i in range(5):
        state = tracker.update(hit_object_id=123)
        if i < 4:
            assert not state.locked, f"Should not lock before frame {i}"
        else:
            assert state.locked, "Should lock after dwell frames"
            assert state.locked_id == 123


def test_selection_tracker_unlock_on_no_hit():
    """Test unlock after grace period."""
    tracker = SelectionTracker(dwell_frames=3, unlock_grace_frames=2)
    
    # Lock target
    for _ in range(3):
        tracker.update(hit_object_id=123)
    
    assert tracker.state.locked
    
    # No hit for grace period → should unlock
    tracker.update(None)
    assert tracker.state.locked  # Still locked (grace 1/2)
    
    tracker.update(None)
    assert not tracker.state.locked  # Unlocked after grace period


def test_selection_tracker_manual_unlock():
    """Test manual unlock."""
    tracker = SelectionTracker(dwell_frames=3, unlock_grace_frames=2)
    
    # Lock target
    for _ in range(3):
        tracker.update(hit_object_id=123)
    
    assert tracker.state.locked
    
    # Manual unlock
    tracker.manual_unlock()
    assert not tracker.state.locked


def test_target_selector_integration(sim):
    """Test TargetSelector with simulator."""
    with open('configs/robotics.yaml', 'r') as f:
        cfg = yaml.safe_load(f)
    
    selector = TargetSelector(sim, cfg)
    
    # Update with no cursor → no target
    state = selector.update(None)
    assert state.locked_id is None


def test_ray_test_returns_valid_type(sim):
    """Test ray_test_object returns int or None."""
    # Test at screen center (may or may not hit cube depending on camera)
    result = sim.ray_test_object(0.5, 0.5)
    assert result is None or isinstance(result, int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])




