# 🚀 QUICK START GUIDE

**Welcome to the Intent Interface + Robotics Prototype!**

This repository contains TWO major systems:
1. **Intent Interface** (Week 9 Complete) - Vision-based intent detection
2. **Robotics Simulation** (Week 1 Complete) - Virtual robot arm

---

## 🎯 Which Demo Should I Run?

### Option 1: Intent Interface Demo (Python 3.13 OK)

**What it does:** Vision-based intent detection with hand gestures

```bash
# Object detection + hand tracking demo
python scripts/run_demo_simple_yolo.py

# OR full system demo (requires all dependencies)
python scripts/run_unified_demo.py --mode full_narrative
```

**Requirements:**
- Python 3.8+ (your current Python 3.13 works!)
- Webcam (optional, mock mode available)
- Dependencies: `pip install -r requirements.txt`

**Status:** ✅ Fully working on your system

---

### Option 2: Robotics Arm Demo (Requires Python 3.12)

**What it does:** 3D physics simulation of KUKA IIWA robot arm

```bash
# Quick start helper
bash RUN_ROBOTICS.sh

# OR manual
python scripts/run_virtual_arm_demo.py
```

**Requirements:**
- ⚠️ **Python 3.12** (not 3.13 - PyBullet compatibility)
- Dependencies: `pip install pybullet scipy`

**Status:** ⚠️ Requires Python 3.12 environment

---

## 📋 Setup Instructions

### Intent Interface (Current Python OK)

```bash
# Install dependencies
pip install -r requirements.txt

# Run demo
python scripts/run_demo_simple_yolo.py

# Run tests
pytest tests/test_final_trust_regressions.py -v
```

### Robotics Simulation (Needs Python 3.12)

```bash
# Create Python 3.12 environment
conda create -n intent-robotics python=3.12 -y
conda activate intent-robotics

# Install dependencies
pip install -r requirements.txt

# Run demo
python scripts/run_virtual_arm_demo.py

# Run tests
pytest tests/test_week1_world_loads.py -v
```

---

## 🎬 What Each Demo Shows

### Intent Interface Demos

**1. Simple YOLO Demo** (`run_demo_simple_yolo.py`)
- Live webcam feed
- YOLOv8 object detection (80 classes)
- Optional hand tracking
- Object tracking with IDs
- Real-time affordance generation

**Expected Output:**
- Camera window with detection boxes
- "person", "cell phone", "laptop", etc. labels
- Persistent tracking IDs
- FPS counter

**2. Hand Gesture Demo** (`run_demo_with_hands.py`)
- Focused on pinch gesture confirmation
- 6-frame hold requirement
- Visual progress bar
- "CONFIRMED!" overlay

**3. Full System Demo** (`run_unified_demo.py`)
- Complete Week 1-9 integration
- Multiple scenarios (happy path, ambiguity, recovery)
- Comprehensive metrics
- Deterministic replay

### Robotics Demo

**Virtual Arm Demo** (`run_virtual_arm_demo.py`)
- 3D PyBullet simulation
- KUKA IIWA robot (7 joints)
- Interactive camera controls
- Table + cube physics
- State inspection

**Expected Output:**
- 3D GUI window
- Robot arm (white/gray)
- Brown table
- Red cube falling due to gravity
- State printouts (joints, EE pose, objects)

---

## 📊 Current Status

| System | Status | Tests | Python |
|--------|--------|-------|--------|
| **Intent Interface** | ✅ Week 9 Complete | 28/28 passing | 3.8+ (3.13 OK) |
| **Robotics Module** | ✅ Week 1 Complete | 25+ passing | 3.12 required |

---

## 📚 Documentation

### Intent Interface
- **Main README**: [README.md](README.md)
- **Demo Guide**: [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)
- **Week 9 Summary**: [WEEK_9_COMPLETE.md](WEEK_9_COMPLETE.md)

### Robotics
- **Module README**: [docs/ROBOTICS_README.md](docs/ROBOTICS_README.md)
- **Setup Guide**: [docs/ROBOTICS_SETUP.md](docs/ROBOTICS_SETUP.md)
- **Week 1 Summary**: [WEEK_1_ROBOTICS_COMPLETE.md](WEEK_1_ROBOTICS_COMPLETE.md)

---

## 🐛 Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'pybullet'"

**Solution:** Install dependencies or use Python 3.12 for robotics

```bash
pip install -r requirements.txt
```

### Issue: "AttributeError: module 'mediapipe' has no attribute 'solutions'"

**Status:** Known issue with MediaPipe 0.10.31 on Python 3.13

**Solution:** Demo gracefully degrades (runs without hand tracking)

**Workaround:** The demo detects this and shows:
```
⚠️  Running without hand detection (install: pip install mediapipe)
```

### Issue: PyBullet won't install

**Cause:** Python 3.13 - PyBullet doesn't have pre-built wheels yet

**Solution:** Use Python 3.12 for robotics demo

```bash
conda create -n intent-robotics python=3.12 -y
conda activate intent-robotics
pip install pybullet
```

---

## ✅ Recommended First Steps

### For Demo/Presentation

```bash
# 1. Quick Intent Interface demo (works now)
python scripts/run_demo_simple_yolo.py

# 2. Setup Python 3.12 for robotics (one-time)
conda create -n intent-robotics python=3.12 -y
conda activate intent-robotics
pip install -r requirements.txt

# 3. Run robotics demo
python scripts/run_virtual_arm_demo.py
```

### For Development

```bash
# 1. Run all Intent Interface tests
pytest tests/ -v -k "not week1_world"

# 2. Setup Python 3.12 environment
conda create -n intent-robotics python=3.12 -y
conda activate intent-robotics
pip install -r requirements.txt

# 3. Run robotics tests
pytest tests/test_week1_world_loads.py -v

# 4. Read documentation
# - docs/ROBOTICS_README.md
# - docs/DEMO_GUIDE.md
```

### For Research

```bash
# 1. Run full system demo with logging
python scripts/run_unified_demo.py --mode full_narrative --seed 42

# 2. Generate metrics report
python scripts/generate_metrics_report.py --format html

# 3. Replay session with explanations
python scripts/replay_session.py logs/session_latest.jsonl --explain

# 4. Verify safety invariants
pytest tests/test_final_trust_regressions.py -v
```

---

## 🎯 What to Expect

### Intent Interface Demo
- ✅ Camera feed with detection overlays
- ✅ Real-time object recognition (80 classes)
- ✅ Object tracking with persistent IDs
- ✅ Affordance generation
- ✅ Hand tracking (if MediaPipe works)
- ⚠️ MediaPipe may not work on Python 3.13 (graceful degradation)

### Robotics Demo
- ⚠️ Requires Python 3.12 setup (one-time)
- ✅ 3D physics simulation
- ✅ Interactive visualization
- ✅ State inspection
- ✅ Full test coverage

---

## 🚀 Ready to Run!

**Simplest start:**
```bash
python scripts/run_demo_simple_yolo.py
```

**For full robotics:**
```bash
bash RUN_ROBOTICS.sh
```

**Questions?**
- Intent Interface: See [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md)
- Robotics: See [docs/ROBOTICS_SETUP.md](docs/ROBOTICS_SETUP.md)

---

## 📞 Support

**Stuck?** Check these files:
- [CAMERA_TROUBLESHOOTING.md](CAMERA_TROUBLESHOOTING.md) - Camera issues
- [docs/ROBOTICS_SETUP.md](docs/ROBOTICS_SETUP.md) - Python 3.12 setup
- [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) - General troubleshooting

**Everything working?** Great! See [README.md](README.md) for full documentation.

---

**Last Updated:** January 7, 2026  
**Intent Interface:** Week 9 Complete ✅  
**Robotics Module:** Week 1 Complete ✅





