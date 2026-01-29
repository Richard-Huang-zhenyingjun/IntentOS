# Week 1: Camera Input Stream - Implementation Complete

## Overview

The camera input stream module provides live camera feed with graceful failure handling. This is the foundation for visual object scoping in Week 1.

## Files Created

### Core Module
- **`src/vision/camera_stream.py`** - Main camera stream implementation
  - `CameraFrame` dataclass - Frame with metadata
  - `CameraConfig` dataclass - Configuration options
  - `CameraStream` class - Camera stream handler

### Tests
- **`tests/test_camera_stream.py`** - Unit tests for camera stream
- **`examples/test_camera_live.py`** - Live test script

## Key Features

✅ **Non-blocking**: `get_frame()` returns `None` if no frame available  
✅ **Graceful degradation**: System continues if camera fails  
✅ **Mock mode**: Deterministic testing without real camera  
✅ **Read-only**: Never mutates core system state  
✅ **Error handling**: Comprehensive exception handling  
✅ **Context manager**: Can be used with `with` statement  

## Usage

### Basic Usage

```python
from src.vision.camera_stream import CameraStream, CameraConfig

# Create config
config = CameraConfig(
    device_index=0,
    width=640,
    height=480,
    target_fps=30,
    mock_mode=False  # Set True for testing
)

# Create and start stream
stream = CameraStream(config, seed=42)
if stream.start():
    # Get frames (non-blocking)
    frame = stream.get_frame()
    if frame is not None:
        print(f"Frame {frame.frame_id}: {frame.width}x{frame.height}")
    
    stream.stop()
```

### Context Manager

```python
with CameraStream(config) as stream:
    frame = stream.get_frame()
    if frame:
        # Process frame
        pass
# Automatically stopped
```

### Mock Mode (Testing)

```python
config = CameraConfig(mock_mode=True, seed=42)
stream = CameraStream(config)
stream.start()

# Deterministic synthetic frames
frame = stream.get_frame()
```

## Configuration Options

- `device_index`: Camera device number (default: 0)
- `target_fps`: Target frames per second (default: 30)
- `width`: Frame width (default: 640)
- `height`: Frame height (default: 480)
- `auto_exposure`: Enable auto exposure (default: True)
- `mock_mode`: Use synthetic frames for testing (default: False)

## Frame Structure

```python
@dataclass
class CameraFrame:
    frame_id: int          # Sequential frame ID
    timestamp: float        # Unix timestamp
    image: np.ndarray      # BGR image array
    width: int             # Frame width
    height: int            # Frame height
    fps: float             # Actual FPS
```

## Safety Properties

1. **One object maximum**: Camera stream doesn't enforce this (handled by scoping logic)
2. **No execution paths**: Camera is read-only, never triggers actions
3. **No state mutation**: Camera stream doesn't modify core system state
4. **Graceful failure**: Returns `None` on failure, system continues
5. **Non-blocking**: Never blocks main event loop

## Testing

### Run Unit Tests

```bash
python -m pytest tests/test_camera_stream.py -v
```

### Test Live Camera

```bash
python examples/test_camera_live.py
```

## Dependencies

- `opencv-python` (cv2) - Camera access
- `numpy` - Image arrays

Install with:
```bash
pip install opencv-python numpy
```

## Integration Notes

The camera stream is designed to integrate with:
- Object detection module (next step)
- System orchestrator (Week 1-9 system)
- UI overlay (visual scoping display)

**Important**: Camera stream is read-only and never mutates core system state. All scoping decisions are made by separate modules.

## Next Steps

1. ✅ Camera input stream - **COMPLETE**
2. ⏭️ Object detection module
3. ⏭️ Visual scoping logic
4. ⏭️ UI overlay integration
5. ⏭️ Safety state updates

