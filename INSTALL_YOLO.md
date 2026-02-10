# Install YOLOv8 for Object Recognition

## Problem
The demo is detecting objects but labeling them as "unknown" because it's using basic contour detection instead of YOLOv8.

## Solution

### Step 1: Install Ultralytics YOLOv8

```bash
pip install ultralytics
```

**What this installs:**
- YOLOv8 object detection framework
- Pre-trained models (auto-downloads ~6MB on first run)
- Support for 80 object classes (COCO dataset)

### Step 2: Run the Complete Demo

```bash
python scripts/run_complete_demo.py
```

**What you'll see:**
```
✅ YOLOv8 nano model loaded (80 object classes)
✅ Object tracker initialized
✅ Affordance engine initialized

🎯 Detection Mode: YOLOv8 (recognizes 80 object types)
   Person, phone, laptop, cup, chair, etc.
```

## Supported Object Classes (80 total)

### Common Objects:
- **People:** person
- **Electronics:** cell phone, laptop, tv, keyboard, mouse, remote
- **Furniture:** chair, couch, bed, dining table, desk
- **Kitchen:** cup, bottle, bowl, knife, spoon, fork
- **Office:** book, scissors, backpack
- **Transport:** car, bicycle, motorcycle, bus, train
- **Animals:** cat, dog, horse, bird
- And 50+ more!

## What Changes?

### Before (Contour Detection):
```
Objects tracked: 1
  - unknown (ID: track_0001, age: 30)
```

### After (YOLO Detection):
```
Objects tracked: 3
  - person (ID: track_0001, age: 120)
  - cell phone (ID: track_0002, age: 45)
  - laptop (ID: track_0003, age: 89)
```

## Performance

- **Model:** YOLOv8n (nano) - optimized for speed
- **Size:** ~6MB download
- **Speed:** 30-60 FPS on CPU
- **Accuracy:** High for common objects
- **Classes:** 80 COCO object types

## Alternative: Use Contour Detection

If you can't install ultralytics or want faster (but generic) detection:

```bash
# The demo automatically falls back to contour detection
python scripts/run_complete_demo.py
```

**Contour mode:**
- ✅ Works without installation
- ✅ Fast (60+ FPS)
- ❌ Labels all objects as "unknown"
- ❌ No object classification

## Troubleshooting

### Import Error: No module named 'ultralytics'

```bash
pip install ultralytics
```

### Model Download Fails

The first run downloads yolov8n.pt (~6MB). If it fails:

```bash
# Manual download
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt
```

Then place `yolov8n.pt` in your working directory.

### Slow Performance

YOLOv8n is already the fastest model. If still slow:

1. Reduce frame size in the script (640x480 → 320x240)
2. Use contour detection (faster but no classification)
3. Skip affordance generation (comment out Step 3)

### Wrong Objects Detected

YOLO is pre-trained on COCO dataset. It works best for:
- Common household objects
- People
- Vehicles
- Animals

It may struggle with:
- Custom/unusual objects
- Heavily occluded objects
- Very small objects

## Summary

```bash
# Quick setup
pip install ultralytics
python scripts/run_complete_demo.py

# You should see real object labels:
# "person", "cell phone", "laptop", "cup", etc.
```

**Total time:** 1 minute  
**Disk space:** ~6MB  
**Result:** Real object recognition! 🎉





