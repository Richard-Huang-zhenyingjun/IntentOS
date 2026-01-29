"""
Demo scenarios - pre-scripted demonstration sequences.
Week 8: Showcase robustness and recovery capabilities.
"""

from typing import List, Tuple
from .fault_injection import ScheduledFault, FaultType


class DemoScenario:
    """Demo scenario with narration and fault schedule."""
    
    def __init__(self, name: str, description: str, faults: List[ScheduledFault], narration: List[Tuple[float, str]]):
        """
        Initialize scenario.
        
        Args:
            name: Scenario name
            description: Scenario description
            faults: Scheduled faults
            narration: List of (time_s, message) narration points
        """
        self.name = name
        self.description = description
        self.faults = faults
        self.narration = narration


# Scenario 1: Happy path (no faults)
HAPPY_PATH = DemoScenario(
    name="happy_path",
    description="Normal operation - gaze select → EEG confirm → grasp object",
    faults=[],
    narration=[
        (0.0, "Scenario: Happy Path - Normal Operation"),
        (1.0, "Lock target with gaze..."),
        (3.0, "System proposes actions..."),
        (5.0, "Confirm with high attention..."),
        (8.0, "Robot executes autonomously..."),
        (12.0, "Grasp complete!"),
    ]
)


# Scenario 2: EEG dropout during reach
EEG_DROPOUT_MID_REACH = DemoScenario(
    name="eeg_dropout_mid_reach",
    description="EEG signal drops during reach → system pauses safely",
    faults=[
        ScheduledFault(time_s=8.0, fault_type=FaultType.EEG_DROPOUT, duration_s=3.0),
    ],
    narration=[
        (0.0, "Scenario: EEG Dropout During Reach"),
        (1.0, "Lock target with gaze..."),
        (3.0, "System proposes REACH_FORWARD..."),
        (5.0, "Confirm with high attention..."),
        (7.0, "Robot begins reaching..."),
        (8.0, "⚠️  EEG SIGNAL LOST!"),
        (8.5, "System PAUSES execution"),
        (9.0, "Robot frozen in safe position"),
        (11.0, "✓ EEG signal restored"),
        (12.0, "Recovery: re-confirm to resume..."),
    ]
)


# Scenario 3: Target loss during confirmation
TARGET_LOSS_DURING_CONFIRM = DemoScenario(
    name="target_loss_during_confirm",
    description="Target disappears while awaiting confirmation → pause and require re-select",
    faults=[
        ScheduledFault(time_s=4.5, fault_type=FaultType.TARGET_LOSS, duration_s=2.5),
    ],
    narration=[
        (0.0, "Scenario: Target Loss During Confirmation"),
        (1.0, "Lock target with gaze..."),
        (3.0, "System proposes REACH_FORWARD..."),
        (4.0, "Awaiting EEG confirmation..."),
        (4.5, "⚠️  TARGET LOST!"),
        (5.0, "System PAUSES (target disappeared)"),
        (5.5, "Must re-acquire target..."),
        (7.0, "✓ Target re-locked"),
        (8.0, "Recovery complete, ready to proceed..."),
    ]
)


# Scenario 4: Cancel after grasp
CANCEL_AFTER_GRASP = DemoScenario(
    name="cancel_after_grasp",
    description="User cancels after grasping → detach and return to rest",
    faults=[],  # User-triggered cancel, not a fault
    narration=[
        (0.0, "Scenario: Cancel After Grasp"),
        (1.0, "Lock target with gaze..."),
        (3.0, "System proposes actions..."),
        (5.0, "Confirm reach..."),
        (8.0, "Confirm grasp..."),
        (12.0, "Object grasped successfully"),
        (13.0, "User decides to cancel..."),
        (13.5, "(Press X to cancel)"),
        (15.0, "System detaches object"),
        (16.0, "Robot returns to rest pose"),
    ]
)


# Scenario 5: High variance (unstable signal)
HIGH_VARIANCE_BLOCKS_CONFIRM = DemoScenario(
    name="high_variance_blocks",
    description="High EEG variance blocks confirmation → requires stable signal",
    faults=[
        ScheduledFault(time_s=4.0, fault_type=FaultType.HIGH_VARIANCE, duration_s=4.0),
    ],
    narration=[
        (0.0, "Scenario: High Variance Blocks Confirmation"),
        (1.0, "Lock target with gaze..."),
        (3.0, "System proposes REACH_FORWARD..."),
        (4.0, "⚠️  EEG signal becomes erratic"),
        (4.5, "Confirmation BLOCKED (high variance)"),
        (5.0, "Decision strategy filters unstable signal"),
        (6.0, "User must stabilize attention..."),
        (8.0, "✓ Signal stabilized"),
        (9.0, "Confirmation now permitted..."),
    ]
)


# Scenario registry
SCENARIOS = {
    "happy_path": HAPPY_PATH,
    "eeg_dropout_mid_reach": EEG_DROPOUT_MID_REACH,
    "target_loss_during_confirm": TARGET_LOSS_DURING_CONFIRM,
    "cancel_after_grasp": CANCEL_AFTER_GRASP,
    "high_variance_blocks": HIGH_VARIANCE_BLOCKS_CONFIRM,
}


def get_scenario(name: str) -> DemoScenario:
    """
    Get scenario by name.
    
    Args:
        name: Scenario name
        
    Returns:
        DemoScenario
        
    Raises:
        ValueError: If scenario not found
    """
    if name not in SCENARIOS:
        available = ", ".join(SCENARIOS.keys())
        raise ValueError(f"Unknown scenario '{name}'. Available: {available}")
    
    return SCENARIOS[name]


def list_scenarios() -> List[str]:
    """Get list of available scenario names."""
    return list(SCENARIOS.keys())




