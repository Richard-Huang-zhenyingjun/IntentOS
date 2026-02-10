import pytest
import numpy as np
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add parent directory so src can be imported as a package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.execution.primitive_executor import PrimitiveExecutor, ExecutorStatus
from src.planning.primitive import Primitive, PrimitiveType
from src.robot.world_state import WorldState
from src.robot.simulator import ArmState


@pytest.fixture
def mock_controller():
    """Mock controller for testing"""
    controller = Mock()
    controller.move_to_position = Mock()
    controller.update = Mock(return_value=False)  # Not complete by default
    controller.is_executing = Mock(return_value=False)
    return controller


@pytest.fixture
def mock_grasp():
    """Mock grasp controller"""
    grasp = Mock()
    grasp.attach = Mock()
    grasp.detach = Mock()
    return grasp


@pytest.fixture
def test_world():
    """Test world state"""
    return WorldState(
        arm=ArmState(
            joint_positions=np.zeros(7),
            ee_position=np.array([0.3, 0.0, 0.8]),
            ee_orientation=np.array([0, 0, 0, 1])
        ),
        object=None,
        target_id=None,
        holding=False,
        attached_id=None
    )


def test_executor_starts_with_idle_status(mock_controller, mock_grasp):
    """Executor should start in IDLE state"""
    executor = PrimitiveExecutor(mock_controller, mock_grasp)
    
    assert executor.status == ExecutorStatus.IDLE
    assert len(executor.active_plan) == 0


def test_executor_starts_plan(mock_controller, mock_grasp):
    """start_plan() should set up execution state"""
    executor = PrimitiveExecutor(mock_controller, mock_grasp)
    
    plan = [
        Primitive(type=PrimitiveType.REACH, target_xyz=np.array([0.2, 0.0, 0.7])),
        Primitive(type=PrimitiveType.GRASP, object_id=10)
    ]
    
    executor.start_plan(plan)
    
    assert executor.status == ExecutorStatus.RUNNING
    assert len(executor.active_plan) == 2
    assert executor.plan_index == 0
    assert executor.active_primitive_started == False


def test_executor_multi_frame_pattern(mock_controller, mock_grasp, test_world):
    """
    Executor should follow multi-frame pattern:
    Frame 1: Start primitive
    Frame 2+: Check completion
    """
    executor = PrimitiveExecutor(mock_controller, mock_grasp)
    
    plan = [
        Primitive(type=PrimitiveType.REACH, target_xyz=np.array([0.2, 0.0, 0.7]))
    ]
    executor.start_plan(plan)
    
    # Frame 1: Start primitive
    status = executor.tick(test_world)
    
    assert status == ExecutorStatus.RUNNING
    assert mock_controller.move_to_position.called
    assert executor.active_primitive_started == True
    # Should NOT call update() in same frame!
    assert not mock_controller.update.called
    
    # Frame 2: Check completion (not complete)
    mock_controller.update.return_value = False
    status = executor.tick(test_world)
    
    assert status == ExecutorStatus.RUNNING
    assert mock_controller.update.called
    assert executor.plan_index == 0  # Still on first primitive
    
    # Frame 3: Check completion (complete)
    mock_controller.update.return_value = True
    status = executor.tick(test_world)
    
    # Should advance to next primitive
    assert executor.plan_index == 1
    assert executor.active_primitive_started == False
    
    # Frame 4: No more primitives
    status = executor.tick(test_world)
    
    assert status == ExecutorStatus.COMPLETE


def test_executor_handles_grasp_primitive(mock_controller, mock_grasp, test_world):
    """GRASP primitive should call grasp.attach()"""
    executor = PrimitiveExecutor(mock_controller, mock_grasp)
    
    plan = [
        Primitive(type=PrimitiveType.GRASP, object_id=42)
    ]
    executor.start_plan(plan)
    
    # Frame 1: Start GRASP
    status = executor.tick(test_world)
    
    assert status == ExecutorStatus.RUNNING
    mock_grasp.attach.assert_called_with(42)
    
    # Frame 2: GRASP completes immediately (Week 1 simplification)
    status = executor.tick(test_world)
    
    assert executor.plan_index == 1  # Advanced


def test_executor_handles_release_primitive(mock_controller, mock_grasp, test_world):
    """RELEASE primitive should call grasp.detach()"""
    executor = PrimitiveExecutor(mock_controller, mock_grasp)
    
    plan = [
        Primitive(type=PrimitiveType.RELEASE, object_id=42)
    ]
    executor.start_plan(plan)
    
    # Frame 1: Start RELEASE
    status = executor.tick(test_world)
    
    assert mock_grasp.detach.called
    
    # Frame 2: RELEASE completes immediately
    status = executor.tick(test_world)
    
    assert executor.plan_index == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
