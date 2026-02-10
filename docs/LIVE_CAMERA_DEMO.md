# Live Camera Demo Guide

**Run the Intent Interface with your real webcam!**

---

## Quick Start

### 1. Test Your Camera First
```bash
python scripts/test_camera.py
```

This will:
- ✅ Check if your camera is accessible
- ✅ Show camera resolution and FPS
- ✅ Display a test frame

### 2. Run the Live Demo
```bash
python scripts/run_live_camera.py
```

---

## What You'll See

### Console Output
```
============================================================
INTENT INTERFACE - LIVE CAMERA DEMO
============================================================

Starting camera...
✅ Camera initialized!

Controls:
  Q or ESC - Quit
  SPACE - Pause/Resume

Looking for objects...
------------------------------------------------------------

[Frame 30 | FPS: 29.8]
  State: SCOPED
  Objects tracked: 2
  ✓ Focused: lamp (confidence: 0.87)
  ✓ Actions available: 2
     1. Toggle Power
     2. Turn On
```

### Status Indicators

| Symbol | Meaning |
|--------|---------|
| ✓ | Success / Available |
| ⚠️ | Warning / Ambiguity |
| ⏸️ | Paused |
| ❌ | Error |

---

## Controls

| Key | Action |
|-----|--------|
| `Q` | Quit demo |
| `ESC` | Quit demo |
| `SPACE` | Pause/Resume processing |

---

## What the System Does

### 1. **Camera Capture** (Week 1)
- Reads frames from your webcam at 30 FPS
- Displays annotated video feed

### 2. **Object Detection** (Week 1)
- Detects objects using contour detection
- No ML required - works out of the box!
- Filters by size and confidence

### 3. **Object Tracking** (Week 2)
- Assigns persistent IDs to objects
- Tracks objects across frames
- Handles occlusions and re-appearances

### 4. **Focus Selection** (Week 2)
- Selects ONE primary object
- Prefers center objects
- Detects ambiguity (multiple objects)

### 5. **Affordance Computation** (Week 3-6)
- Infers what actions are possible
- Maximum 2 actions shown
- Shows confidence levels

### 6. **State Inference** (Week 6)
- Estimates object state (on/off, open/closed)
- Uses visual heuristics

### 7. **Safety Monitoring** (Week 7-8)
- Detects failures
- Pauses on ambiguity
- Shows recovery instructions

---

## Troubleshooting

### "Could not open camera"

**macOS:**
1. Open System Preferences → Security & Privacy → Camera
2. Allow Terminal/Python to access camera
3. Restart Terminal

**Linux:**
```bash
# Check if camera exists
ls /dev/video*

# Check permissions
sudo usermod -a -G video $USER
# Then log out and back in
```

**Windows:**
1. Settings → Privacy → Camera
2. Allow desktop apps to access camera

### "ModuleNotFoundError: No module named 'cv2'"

Install OpenCV:
```bash
pip install opencv-python
```

### "Permission denied when creating logs"

Create logs directory manually:
```bash
mkdir -p logs/video_sessions
chmod 755 logs
```

### Camera shows black screen

1. Check if another app is using camera (Zoom, Skype, etc.)
2. Try a different device ID:
   ```bash
   # Edit scripts/run_live_camera.py, change:
   'device_id': 0  # Try 1, 2, 3...
   ```

### Low FPS / Lag

Reduce resolution in `scripts/run_live_camera.py`:
```python
'camera': {
    'width': 320,   # Lower resolution
    'height': 240,
    'fps': 15       # Lower FPS target
}
```

---

## Demo Modes

### Safe Mode (Default)
```python
'execution': {'enabled': False}
```
- ✅ Camera, detection, tracking work
- ✅ Shows affordances
- ❌ No actual execution (safe for testing)

### Full Mode (Advanced)
```python
'execution': {'enabled': True},
'gesture': {'enabled': True}
```
- ✅ Full system active
- ✅ Can execute actions with pinch gesture
- ⚠️ Requires hand tracking (MediaPipe)

---

## Expected Performance

| Metric | Value |
|--------|-------|
| FPS (no processing) | 30 FPS |
| FPS (with detection) | 20-30 FPS |
| FPS (full pipeline) | 15-25 FPS |
| Latency | < 50ms |
| Objects tracked | Up to 10 |

---

## Configuration Options

Edit `scripts/run_live_camera.py` to customize:

### Camera Settings
```python
'camera': {
    'device_id': 0,      # 0 = default, 1 = external
    'width': 640,        # Resolution width
    'height': 480,       # Resolution height
    'fps': 30            # Target FPS
}
```

### Detection Settings
```python
'detection': {
    'mode': 'contour',        # 'contour' or 'mock'
    'min_confidence': 0.5,    # 0.0-1.0
    'min_area_pixels': 1000   # Minimum object size
}
```

### Tracking Settings
```python
'tracking': {
    'track_max_age_frames': 10,  # How long to keep lost tracks
    'track_min_hits': 3          # Hits needed to confirm track
}
```

---

## Demo Scenarios

### Scenario 1: Single Object Detection
**Setup:** Place one object (cup, phone, lamp) in view

**Expected:**
```
State: SCOPED
Objects tracked: 1
✓ Focused: lamp (confidence: 0.92)
✓ Actions available: 2
   1. Toggle Power
   2. Turn On
```

### Scenario 2: Multiple Objects (Ambiguity)
**Setup:** Place two objects side-by-side

**Expected:**
```
State: IDLE
Objects tracked: 2
⚠️ Ambiguity: Two objects competing (margin=0.15)
```

### Scenario 3: Object Tracking
**Setup:** Move an object slowly across frame

**Expected:**
- Object maintains same track ID
- Bounding box follows smoothly
- Confidence stays high

### Scenario 4: Occlusion Recovery
**Setup:** Temporarily cover an object with hand

**Expected:**
- Track ages out after ~10 frames
- Recovers when object visible again
- May get new track ID if gone too long

---

## Output Files

### Logs
```
logs/
├── events.jsonl              # All system events
└── video_sessions/
    └── session_XXXXX.jsonl   # Camera frames logged
```

### Analysis
```bash
# View logged events
cat logs/events.jsonl | jq

# Count detections
grep "detection_run" logs/events.jsonl | wc -l

# View tracking info
grep "tracking_result" logs/events.jsonl | jq
```

---

## Advanced Usage

### Record Session
```python
# In run_live_camera.py, add:
'video_session': {
    'enabled': True,
    'log_every_frame': True  # Log all frames (large!)
}
```

### Replay Recorded Session
```bash
python scripts/replay_session.py logs/video_sessions/session_XXXXX.jsonl
```

### Generate Metrics Report
```bash
python scripts/generate_metrics_report.py logs/video_sessions/session_XXXXX.jsonl
```

---

## Safety Notes

⚠️ **This demo is safe:**
- Execution is disabled by default
- No actions actually executed
- No hardware controlled
- Only vision pipeline active

✅ **To enable full execution:**
1. Review safety docs: `docs/SAFETY_GUARANTEES.md`
2. Connect to Smart World Simulator
3. Enable execution in config
4. Use pinch gesture for confirmation

---

## FAQ

### Q: Why is detection slow?
**A:** Contour detection is simple but not optimized. For better performance:
- Use mock mode: `'mode': 'mock'`
- Or integrate YOLOv8 (future work)

### Q: Can I use an external camera?
**A:** Yes! Change `'device_id': 0` to `1`, `2`, etc.

### Q: Does this work without GPU?
**A:** Yes! Contour detection is CPU-only.

### Q: Can I run this headless (no display)?
**A:** Yes, but you'll need to disable OpenCV windows:
```python
# Comment out cv2.imshow() calls
# Keep processing logic
```

### Q: How do I integrate YOLO?
**A:** See `docs/YOLO_INTEGRATION.md` (future)

---

## What's Next?

After testing the live camera:

1. **Try gesture control:**
   ```bash
   python scripts/run_live_camera.py --with-gestures
   ```

2. **Run full demo:**
   ```bash
   python scripts/run_unified_demo.py --mode full_narrative
   ```

3. **Review safety tests:**
   ```bash
   pytest tests/test_trust_regressions.py -v
   ```

---

## Support

**Camera issues?**
- Run `scripts/test_camera.py` first
- Check permissions
- Try different device IDs

**Import errors?**
- Ensure you're in project root
- Check Python path: `echo $PYTHONPATH`
- Re-run import fix: `python fix_imports.py`

**Performance issues?**
- Lower resolution
- Use mock detector
- Close other camera apps

---

**🎥 Ready to try it? Run `python scripts/test_camera.py` first!** 📹✨

**Date:** December 31, 2024  
**Version:** Week 9 Complete  
**Status:** Production Ready





