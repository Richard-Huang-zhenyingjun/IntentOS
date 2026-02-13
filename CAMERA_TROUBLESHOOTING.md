# Camera Troubleshooting Guide

**Problem:** Camera shows static/noise instead of video feed

---

## Quick Diagnosis

Run these tests in order:

### Test 1: Minimal Camera Test (30 seconds)
```bash
python test_camera_minimal.py
```

**What it tests:** Basic OpenCV camera access

**Expected:** Window with live video feed

**If it fails:**
- ❌ Camera permissions issue
- ❌ Wrong device ID
- ❌ Camera in use by another app

---

### Test 2: Live Display Test (1 minute)
```bash
python scripts/run_live_with_display.py
```

**What it tests:** Camera with system orchestrator

**Expected:** Live feed with FPS counter and frame number

**If it fails:**
- ❌ Orchestrator interfering with camera
- ❌ Configuration issue

---

## Common Issues & Fixes

### Issue 1: "Cannot open camera"

**Symptoms:**
```
Camera opened: False
❌ Cannot open camera
```

**Fix on macOS:**
1. Open System Preferences
2. Security & Privacy → Camera
3. Enable for Terminal (or Python/iTerm)
4. Restart Terminal
5. Try again

**Fix on Linux:**
```bash
# Check if camera exists
ls -la /dev/video*

# Add user to video group
sudo usermod -a -G video $USER

# Log out and back in
```

**Fix on Windows:**
1. Settings → Privacy → Camera
2. Allow desktop apps to access camera
3. Restart

---

### Issue 2: "Can't read frame"

**Symptoms:**
```
Camera opened: True
❌ Can't read frame
```

**Possible causes:**
1. **Camera busy** - Close Zoom, Skype, FaceTime, etc.
2. **Wrong device ID** - Try different IDs
3. **Driver issue** - Update camera drivers

**Try different device IDs:**
```python
# Edit test_camera_minimal.py
cap = cv2.VideoCapture(0)  # Try 0, 1, 2, 3...
```

---

### Issue 3: Static/noise instead of video

**Symptoms:**
- Window opens
- Shows gray static or random noise
- No actual video feed

**This is the issue you're experiencing!**

**Root cause:** Camera opening but frames not reading correctly

**Fix:**
Use the simplified scripts that bypass the orchestrator:

```bash
# Step 1: Test basic camera (should work)
python test_camera_minimal.py

# Step 2: Test with display (should work)
python scripts/run_live_with_display.py
```

These scripts:
- Open camera directly with OpenCV
- Don't use orchestrator's camera system
- Read frames in a simple loop
- Display directly

---

### Issue 4: Low FPS / Lag

**Symptoms:**
- Video is choppy
- FPS < 10

**Fixes:**
1. **Lower resolution:**
```python
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
```

2. **Disable processing:**
```python
config = {
    'detection': {'enabled': False},
    'tracking': {'enabled': False}
}
```

3. **Close other apps**

---

## Diagnostic Commands

### Check camera access:
```bash
# List video devices (Linux/macOS)
ls -la /dev/video*

# Check with v4l2 (Linux)
v4l2-ctl --list-devices
```

### Test with system camera app:
- **macOS:** Photo Booth
- **Windows:** Camera app
- **Linux:** Cheese, guvcview

If system camera app works but Python doesn't → permissions issue

---

## Testing Strategy

### Level 1: System Camera App
✅ If this works → Camera hardware OK

### Level 2: Minimal Python Test
```bash
python test_camera_minimal.py
```
✅ If this works → OpenCV + permissions OK

### Level 3: Simplified Display
```bash
python scripts/run_live_with_display.py
```
✅ If this works → Camera integration OK

### Level 4: Full System
```bash
python scripts/run_live_camera.py
```
✅ If this works → Everything OK!

---

## Script Comparison

| Script | Complexity | What it tests |
|--------|-----------|---------------|
| `test_camera_minimal.py` | Simplest | Raw OpenCV access |
| `scripts/run_live_with_display.py` | Simple | OpenCV + basic overlay |
| `scripts/run_live_camera.py` | Full | Complete system |

**Start with simplest and work up!**

---

## Expected Output

### test_camera_minimal.py:
```
============================================================
MINIMAL CAMERA TEST
============================================================

Opening camera 0...
Camera opened: True
✅ Camera opened!

Reading frames... (Press Q to quit)
------------------------------------------------------------
Frame 30 - Shape: (480, 640, 3)
Frame 60 - Shape: (480, 640, 3)
...

============================================================
✅ Total frames captured: 287
============================================================

✅ SUCCESS - Camera is working!
```

### run_live_with_display.py:
```
============================================================
LIVE CAMERA WITH DISPLAY
============================================================

Testing direct camera access...

✅ Camera working!
   Resolution: 640x480
   Channels: 3
   Dtype: uint8

Creating system orchestrator...
✅ Orchestrator ready

[Window shows live video with green text overlay]
Frame: 123
FPS: 29.8
Camera Feed Active
```

---

## Still Not Working?

### Last Resort Debugging:

1. **Check OpenCV installation:**
```bash
python -c "import cv2; print(cv2.__version__)"
# Should print version like 4.8.0
```

2. **Reinstall OpenCV:**
```bash
pip uninstall opencv-python
pip install opencv-python
```

3. **Try different backend:**
```python
# Add before VideoCapture
cv2.CAP_DSHOW  # Windows
cv2.CAP_AVFOUNDATION  # macOS
cv2.CAP_V4L2  # Linux
```

4. **Check USB:**
- Try different USB port
- Try external webcam
- Check USB permissions

---

## Success Criteria

✅ **Minimal test passes** → Camera access works  
✅ **Display test passes** → Integration works  
✅ **Full demo works** → System complete  

---

## Quick Reference

```bash
# Test sequence:
cd "/Users/richardhuang/Intent Interface Prototype "

# 1. Minimal test
python test_camera_minimal.py

# 2. Display test  
python scripts/run_live_with_display.py

# 3. Full demo
python scripts/run_live_camera.py
```

---

## Get Help

**If minimal test fails:**
- Camera/permissions issue
- Check System Preferences → Camera
- Try different device ID

**If display test fails:**
- Configuration issue
- Check config in script
- Try disabling features

**If full demo fails:**
- Integration issue
- Check orchestrator logs
- Report error message

---

**Date:** December 31, 2024  
**Issue:** Static noise instead of video  
**Solution:** Use simplified scripts  
**Status:** Diagnostic tools ready






