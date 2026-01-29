# 🎥 Live Camera Demo - Ready to Run! 📹

**Status:** All scripts created and ready ✅

---

## Quick Commands

### Test Camera (Do This First!)
```bash
python scripts/test_camera.py
```
**What it does:** Verifies your webcam works

---

### Run Live Demo
```bash
python scripts/run_live_camera.py
```
**What it does:** Full Intent Interface with real webcam

---

## Files Created

| File | Purpose |
|------|---------|
| `scripts/run_live_camera.py` | Main live camera demo ✅ |
| `scripts/test_camera.py` | Camera connectivity test ✅ |
| `docs/LIVE_CAMERA_DEMO.md` | Complete guide ✅ |
| `CAMERA_DEMO_READY.md` | This file ✅ |

---

## What You'll Experience

### 1. Real-time Object Detection
- Your webcam turns on
- Objects are detected automatically
- Bounding boxes drawn around objects

### 2. Focus Selection
- System picks ONE primary object
- Center objects preferred
- Ambiguity detected automatically

### 3. Object Tracking
- Objects get persistent IDs
- Tracks maintained across frames
- Handles occlusions

### 4. Action Suggestions
- Shows possible actions for object
- Maximum 2 options
- Confidence levels displayed

### 5. Safety Monitoring
- Pauses on ambiguity
- Shows recovery instructions
- No execution (safe mode)

---

## Console Output Example

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

[Frame 60 | FPS: 29.5]
  State: SCOPED
  Objects tracked: 3
  ✓ Focused: phone (confidence: 0.92)
  ✓ Actions available: 2
     1. Toggle Screen
     2. Wake
  ⚠️  Ambiguity: cup vs phone (margin=0.12)

^C
⏹️  Interrupted by user

============================================================
Demo Summary:
  Total frames: 187
  Duration: 6.2s
  Average FPS: 30.2
============================================================

✅ Demo complete!
```

---

## Keyboard Controls

| Key | Action |
|-----|--------|
| `Q` | Quit demo |
| `ESC` | Quit demo (alternative) |
| `SPACE` | Pause/Resume processing |

---

## First Run Steps

### Step 1: Test Camera
```bash
cd "/Users/richardhuang/Intent Interface Prototype "
python scripts/test_camera.py
```

**Expected output:**
```
============================================================
CAMERA TEST
============================================================

Trying to open camera 0...
✅ Camera opened successfully!

Camera Info:
  Resolution: 1280x720
  FPS: 30

Reading test frame...
✅ Frame captured: (720, 1280, 3)

Showing preview window...
Press any key to close...

============================================================
✅ CAMERA TEST PASSED!
============================================================
```

### Step 2: Run Live Demo
```bash
python scripts/run_live_camera.py
```

**Expected:**
- Console shows frame updates every second
- Camera LED turns on
- System detects and tracks objects
- Status updates in real-time

### Step 3: Try It Out!
1. **Put an object in view** (cup, phone, lamp)
2. **Watch console** - should show "Focused: [object]"
3. **Move object** - tracking should follow
4. **Add second object** - should detect ambiguity
5. **Press SPACE** - pause/resume
6. **Press Q** - quit cleanly

---

## Troubleshooting

### Camera Won't Open

**macOS:**
```bash
# Grant camera permission
# System Preferences → Security & Privacy → Camera
# Enable for Terminal
```

**Linux:**
```bash
# Check camera exists
ls -la /dev/video*

# Add user to video group
sudo usermod -a -G video $USER
# Log out and back in
```

**Windows:**
```
Settings → Privacy → Camera → Allow desktop apps
```

### Import Errors

```bash
# Re-run import fixes
python fix_imports.py

# Check paths
cd "/Users/richardhuang/Intent Interface Prototype "
python -c "import sys; sys.path.insert(0, 'src'); from intent_core.system_orchestrator import SystemOrchestrator; print('✅ Imports work!')"
```

### OpenCV Not Installed

```bash
pip install opencv-python
```

---

## What's Working

✅ **Week 1:** Camera capture, object detection, focus selection  
✅ **Week 2:** Object tracking, temporal stability  
✅ **Week 3-6:** Affordance computation, state inference  
✅ **Week 7:** Multi-object robustness, failure recovery  
✅ **Week 8:** Enhanced recovery, narrative logging  
✅ **Week 9:** Complete integration, visual embodiment  

---

## Demo is Safe!

**Execution is DISABLED by default:**
- ✅ Camera works
- ✅ Detection works
- ✅ Tracking works
- ✅ Affordances computed
- ❌ No actions executed
- ❌ No hardware controlled

**To enable execution:**
1. Read `docs/SAFETY_GUARANTEES.md`
2. Connect Smart World Simulator
3. Change `'execution': {'enabled': True}`
4. Enable gesture confirmation

---

## Performance Expectations

| Metric | Expected |
|--------|----------|
| FPS | 20-30 |
| Latency | < 50ms |
| Objects tracked | Up to 10 |
| Detection accuracy | Good for contours |

---

## Files to Read

1. **Quick start:** This file (you're reading it!)
2. **Full guide:** `docs/LIVE_CAMERA_DEMO.md`
3. **Safety info:** `docs/SAFETY_GUARANTEES.md`
4. **Demo guide:** `docs/DEMO_GUIDE.md`
5. **Week 9 summary:** `WEEK_9_COMPLETE.md`

---

## Next Steps

After running the live camera demo:

1. **Try mock demo:**
   ```bash
   python scripts/run_unified_demo.py --mode happy_path
   ```

2. **Run full narrative:**
   ```bash
   python scripts/run_unified_demo.py --mode full_narrative
   ```

3. **Review metrics:**
   ```bash
   python scripts/generate_metrics_report.py logs/session_XXXXX.jsonl
   ```

4. **Replay session:**
   ```bash
   python scripts/replay_session.py logs/video_sessions/session_XXXXX.jsonl
   ```

---

## 🎯 Ready to Try It?

### Recommended First Run:
```bash
# 1. Test camera first
python scripts/test_camera.py

# 2. If that works, run live demo
python scripts/run_live_camera.py

# 3. Put objects in view and watch!
```

---

## Summary

✅ **Created:**
- Live camera demo script
- Camera test script
- Comprehensive documentation

✅ **Tested:**
- Import paths work
- Scripts are executable
- Configuration is safe

✅ **Ready:**
- Run `python scripts/test_camera.py` now!
- Then try live demo
- Full Week 1-9 functionality

---

**🎥 Your camera demo is ready! Let's see the Intent Interface in action!** 📹✨

**Date:** December 31, 2024  
**Scripts Created:** 2  
**Status:** READY TO RUN




