"""
Perception module - object state tracking and gaze-based selection.
Week 2: Object pose/velocity reading from PyBullet.
Week 3: Gaze estimation + target selection.
"""

from .object_state import ObjectState, read_object_state
from .selection_cursor import SelectionCursor
from .gaze_estimator import GazeEstimator
from .selection_state import SelectionTracker, SelectionState
from .target_selector import TargetSelector

__all__ = [
    'ObjectState',
    'read_object_state',
    'SelectionCursor',
    'GazeEstimator',
    'SelectionTracker',
    'SelectionState',
    'TargetSelector',
]
