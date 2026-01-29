# How to Run the Demo

## Step 1: Verify Setup

First, run the test script to check for issues:

```bash
python test_demo_setup.py
```

This will check:
- ✅ All required files exist
- ✅ Python version is compatible
- ✅ Required modules (yaml, tkinter) are installed
- ✅ Project modules can be imported
- ✅ Config file loads correctly

## Step 2: Fix Any Issues

### If `yaml` is missing:
```bash
pip install pyyaml
```

### If `tkinter` is missing:
- **Mac**: Usually included with Python. If not, reinstall Python.
- **Linux**: `sudo apt-get install python3-tk`

### If files are missing:
Make sure you're in the project root directory:
```bash
cd /Users/richardhuang/Intent-Interface-Prototype
# OR
cd "/Users/richardhuang/Intent Interface Prototype "
```

## Step 3: Run the Demo

Once all checks pass:

```bash
python scripts/run_unified_demo.py --mode full_narrative
```

## Available Modes

- `--mode single` - Single user demo
- `--mode multi_user` - Multi-user demo
- `--mode fault_injection` - Stress test with faults
- `--mode full_narrative` - Complete narrative demo (recommended)

## What to Expect

1. **Console Output**: Startup messages and periodic status updates
2. **GUI Window Opens**: 
   - **Left side**: Three colored squares (objects)
   - **Right side**: Dark panel showing system reasoning in real-time
3. **Visualizer Updates**: Every 500ms showing:
   - System Status (IDLE, SCOPED, CONFIRMING, EXECUTING, PAUSED)
   - Intent Timeline (last 5 events)
   - Authority Gates (safety checks with ✅/❌)
   - Multi-object state
   - Multi-user state
   - Predictions & Proposals
   - Recovery & Undo status

## Troubleshooting

### Error: "No such file or directory"
**Solution**: Make sure you're in the project root:
```bash
pwd
# Should show: .../Intent-Interface-Prototype
# OR: .../Intent Interface Prototype 
```

### Error: "ModuleNotFoundError: No module named 'yaml'"
**Solution**: Install PyYAML:
```bash
pip install pyyaml
```

### Error: "ModuleNotFoundError: No module named 'src'"
**Solution**: Run from project root:
```bash
cd /Users/richardhuang/Intent-Interface-Prototype
python scripts/run_unified_demo.py --mode full_narrative
```

### Window doesn't open
**Solution**: Check tkinter:
```bash
python3 -c "import tkinter; print('tkinter OK')"
```

### Script runs but nothing happens
**Solution**: Check console output for errors. The GUI should open automatically.

## Quick Test

Test imports quickly:
```bash
python3 -c "import sys; sys.path.insert(0, '.'); from src.intent_core.system_orchestrator import SystemOrchestrator; print('✅ OK')"
```

