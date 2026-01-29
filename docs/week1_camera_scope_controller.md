# Week 1: Camera Scope Controller - Bridge Implementation Complete

## Overview

The camera scope controller bridges the camera pipeline to the core system. It translates camera focus results into system scope signals, enforcing camera-specific safety rules.

## Files Created

### Core Module
- **`src/vision/camera_scope_controller.py`** - Camera scope controller implementation
  - `CameraScopeSignal` dataclass - Signal sent to core system
  - `CameraScopeState` dataclass - Controller internal state
  - `CameraScopeController` class - Bridge logic

### Schema
- **`src/intent_core/schema.py`** - Core schema with SystemState enum

### Configuration
- **`configs/vision.yaml`** - Updated with controller config

### Tests
- **`tests/test_camera_scope_controller.py`** - Unit tests
- **`examples/test_camera_scope_controller.py`** - Test script

## Key Features

✅ **SUGGESTER, not COMMANDER**: Suggests state, core decides  
✅ **Read-only**: Never mutates core system state  
✅ **No execution**: Camera scope ≠ execution permission  
✅ **Safety-aware**: Enforces camera-specific rules  
✅ **Explainable**: Human-readable reasons for signals  
✅ **State tracking**: Monitors frames, scopes, ambiguities  

## Data Structures

### CameraScopeSignal

```python
@dataclass
class CameraScopeSignal:
    # What was detected
    scoped_object_id: Optional[str]
    object_label: Optional[str]
    bbox: Optional[Tuple[int, int, int, int]]
    confidence: float
    
    # Why this decision
    focus_reason: str
    ambiguity_detected: bool
    
    # Metadata
    frame_id: int
    timestamp: float
    
    # Suggested system state (core decides if it accepts)
    suggested_state: SystemState  # IDLE, SCOPED, or PAUSED
```

### CameraScopeState

```python
@dataclass
class CameraScopeState:
    current_scope: Optional[CameraScopeSignal]
    last_update: float
    frames_processed: int
    scopes_created: int
    ambiguities_detected: int
```

## Processing Logic

### Case 1: Ambiguity Detected
```python
if focus_result.ambiguity_detected:
    return CameraScopeSignal(
        suggested_state=SystemState.PAUSED,
        reason="multiple objects",
        ambiguity_detected=True
    )
```

### Case 2: No Object
```python
if focus_result.primary_object is None:
    return CameraScopeSignal(
        suggested_state=SystemState.IDLE,
        reason="no focus",
        ambiguity_detected=False
    )
```

### Case 3: Low Confidence Object
```python
if obj.confidence < min_scope_confidence:
    return CameraScopeSignal(
        suggested_state=SystemState.IDLE,
        reason="low confidence",
        ambiguity_detected=False
    )
```

### Case 4: Confident Scope
```python
if obj.confidence >= min_scope_confidence:
    return CameraScopeSignal(
        suggested_state=SystemState.SCOPED,
        reason="focused on {label}",
        ambiguity_detected=False
    )
```

## Usage

### Basic Usage

```python
from src.vision.camera_scope_controller import CameraScopeController
from src.vision.focus_selector import FocusSelector
from src.vision.object_detector import create_detector
import yaml

# Load config
with open("configs/vision.yaml") as f:
    config = yaml.safe_load(f)

# Create components
detector = create_detector(config, seed=42)
selector = FocusSelector(config["focus_selection"])
controller = CameraScopeController(config["camera_scope_controller"])

# Process frame
detection_result = detector.detect(frame)
focus_result = selector.select(detection_result, frame.width, frame.height)
scope_signal = controller.process_frame(focus_result, frame.frame_id, frame.timestamp)

# Check signal
if scope_signal.suggested_state == SystemState.SCOPED:
    print(f"Scope suggested: {scope_signal.object_label}")
elif scope_signal.suggested_state == SystemState.PAUSED:
    print(f"Paused: {scope_signal.focus_reason}")
```

## Configuration

```yaml
camera_scope_controller:
  min_scope_confidence: 0.6  # Minimum confidence to suggest SCOPED state
```

## Critical Properties

### SUGGESTER, not COMMANDER

- **Suggests** `SystemState.SCOPED`, but core system decides if it accepts
- Core safety gates can still refuse (e.g., if identity invalid)
- Camera scope ≠ execution permission

### Read-Only

- Never mutates core system state
- Only emits signals
- State tracking is for monitoring only

### No Execution

- Camera scope does NOT trigger actions
- Scope is a suggestion, not a command
- Execution requires separate confirmation

## Safety Properties

1. **One object maximum**: Only one object per signal
2. **No execution**: Scope doesn't trigger actions
3. **Read-only**: Never mutates core system state
4. **Ambiguity → PAUSED**: Returns PAUSED when ambiguous
5. **Low confidence → IDLE**: Returns IDLE when confidence too low
6. **Conservative**: When in doubt, suggests IDLE or PAUSED

## Testing

### Run Unit Tests

```bash
python -m pytest tests/test_camera_scope_controller.py -v
```

### Test Controller

```bash
python examples/test_camera_scope_controller.py
```

## Integration Notes

The camera scope controller integrates with:
- Focus selector (input: FocusResult)
- Core system (output: CameraScopeSignal)
- System orchestrator (Week 1-9 system)
- Safety gates (core decides if signal is accepted)

**Important**: The controller is a SUGGESTER, not a COMMANDER. It suggests system state, but the core system decides if it accepts the suggestion. All safety gates remain in place.

## Next Steps

1. ✅ Camera input stream - **COMPLETE**
2. ✅ Object detection - **COMPLETE**
3. ✅ Focus selection - **COMPLETE**
4. ✅ Camera scope controller - **COMPLETE**
5. ⏭️ Visual overlay (display scope visually)
6. ⏭️ Integration with SystemOrchestrator
7. ⏭️ Safety state updates

