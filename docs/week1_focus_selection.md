# Week 1: Focus Selector - Core Logic Implementation Complete

## Overview

The focus selector is the **core logic** of Week 1. It chooses at most ONE object as primary focus from detected objects, detecting ambiguity when multiple objects compete.

## Files Created

### Core Module
- **`src/vision/focus_selector.py`** - Focus selection implementation
  - `FocusCandidate` dataclass - Scored candidate for selection
  - `FocusResult` dataclass - Selection result with explanation
  - `FocusSelector` class - Core selection logic

### Configuration
- **`configs/vision.yaml`** - Updated with focus selection config

### Tests
- **`tests/test_focus_selector.py`** - Unit tests
- **`examples/test_focus_selection.py`** - Test script

## Key Features

✅ **One object maximum**: Always selects at most one primary focus  
✅ **Ambiguity detection**: Detects when scores are too close  
✅ **Center-weighted**: Prefers objects near frame center  
✅ **Deterministic**: Same inputs → same output  
✅ **Conservative**: Returns None when ambiguous  
✅ **Explainable**: Human-readable reasons for decisions  
✅ **Stateless**: No memory between calls  

## Data Structures

### FocusCandidate

```python
@dataclass
class FocusCandidate:
    object: DetectedObject
    center_distance: float      # pixels from frame center
    center_score: float         # 0.0-1.0 (inverse of distance)
    size_score: float          # 0.0-1.0 (normalized area)
    confidence_score: float    # from detection
    total_score: float         # weighted combination
```

### FocusResult

```python
@dataclass
class FocusResult:
    primary_object: Optional[DetectedObject]
    ambiguity_detected: bool
    reason: str  # human-readable explanation
    candidates_considered: int
    runner_up_object: Optional[DetectedObject]
    score_margin: float  # difference between 1st and 2nd
    timestamp: float
```

## Selection Algorithm

### Step 1: Filter
- Remove objects with `confidence < min_confidence`

### Step 2: Score
For each candidate:
```python
center_score = 1.0 / (1.0 + center_distance / frame_diagonal)
size_score = normalized_area  # 0.0 - 1.0
confidence_score = detection_confidence

total_score = (weight_center * center_score +
               weight_size * size_score +
               weight_confidence * confidence_score)
```

### Step 3: Rank
- Sort candidates by `total_score` (descending)

### Step 4: Ambiguity Check
```python
if len(candidates) >= 2:
    margin = candidates[0].score - candidates[1].score
    if margin < min_score_margin:
        return ambiguity=True, primary=None
```

### Step 5: Return
- **Ambiguous**: `primary=None`, `ambiguity=True`
- **No candidates**: `primary=None`, `ambiguity=False`, reason="no objects"
- **Clear winner**: `primary=top_candidate`, `ambiguity=False`

## Usage

### Basic Usage

```python
from src.vision.focus_selector import FocusSelector
from src.vision.object_detector import create_detector
from src.vision.camera_stream import CameraStream, CameraConfig
import yaml

# Load config
with open("configs/vision.yaml") as f:
    config = yaml.safe_load(f)

# Create components
detector = create_detector(config, seed=42)
selector = FocusSelector(config["focus_selection"])
camera = CameraStream(CameraConfig(mock_mode=True), seed=42)
camera.start()

# Process frame
frame = camera.get_frame()
if frame:
    # Detect objects
    detection_result = detector.detect(frame)
    
    # Select focus
    focus_result = selector.select(
        detection_result,
        frame.width,
        frame.height
    )
    
    if focus_result.primary_object:
        print(f"Focus: {focus_result.primary_object.label}")
    elif focus_result.ambiguity_detected:
        print(f"Ambiguity: {focus_result.reason}")
    else:
        print(f"No focus: {focus_result.reason}")

camera.stop()
```

## Configuration

```yaml
focus_selection:
  min_confidence: 0.5
  min_score_margin: 0.2  # 20% difference required
  center_reticle_radius: 50  # pixels
  weight_center: 0.6      # Weight for center distance
  weight_size: 0.2        # Weight for size
  weight_confidence: 0.2  # Weight for confidence
```

## Selection Rules (Strict Priority)

1. **Filter**: Ignore objects with `confidence < min_confidence`
2. **Score**: Calculate weighted combination of:
   - Center distance (closer = higher score)
   - Size (larger = higher score)
   - Confidence (higher = higher score)
3. **Rank**: Sort by `total_score` descending
4. **Ambiguity**: If `margin < min_score_margin` → return None
5. **Return**: Primary object or None

## Key Properties

### Stateless
- No memory between calls
- Each selection is independent
- Week 2 will add tracking

### Deterministic
- Same inputs → same output
- Uses deterministic scoring
- No randomness

### Conservative
- When in doubt → return None
- Ambiguity → wait (don't force choice)
- Unstable → no focus

## Safety Properties

1. **One object maximum**: Never selects more than one
2. **No execution**: Selection doesn't trigger actions
3. **Read-only**: Never mutates core system state
4. **Ambiguity → WAIT**: Returns None when ambiguous
5. **Unstable → IDLE**: Returns None when no clear focus

## Testing

### Run Unit Tests

```bash
python -m pytest tests/test_focus_selector.py -v
```

### Test Focus Selection

```bash
python examples/test_focus_selection.py
```

## Integration Notes

The focus selector integrates with:
- Object detector (input: DetectionResult)
- Camera stream (for frame dimensions)
- System orchestrator (Week 1-9 system)
- UI overlay (display selected focus)

**Important**: Focus selection is stateless and read-only. It never mutates core system state. All scoping decisions are made here, but execution is handled by separate modules.

## Next Steps

1. ✅ Camera input stream - **COMPLETE**
2. ✅ Object detection - **COMPLETE**
3. ✅ Focus selection - **COMPLETE**
4. ⏭️ Visual overlay (display focus visually)
5. ⏭️ Safety state updates
6. ⏭️ Integration with SystemOrchestrator

