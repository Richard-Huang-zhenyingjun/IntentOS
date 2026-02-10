# Intent-Authorized Arm Demo

## Quick Start
```bash
python scripts/run_demo.py --seed 42
```

## What You'll See
- Messy table with scattered objects
- Arm in home position
- Overlay showing: state, proposal, trust level

## Controls
- L — Lock target
- C — Confirm
- X — Cancel
- R — Reset world
- Q — Quit

## Expected Behavior
1. Press L → arm selects nearest object (state: SELECTING → CONFIRMING)
2. Overlay shows proposed action
3. Press C → arm executes pick-place (state: EXECUTING)
4. Watch trust metrics update
5. Repeat until table clean

## Safety Invariant
**false_executions == 0** — arm NEVER moves without your explicit C confirmation

## Troubleshooting
- If arm doesn't move: check diagnostics on startup
- If trust drops: intentional penalty system, reset with R
- If EEG enabled but no device: system falls back to keyboard automatically

## Configuration
Edit `configs/default.yaml` to:
- Enable/disable Gemini advisory proposals
- Enable/disable EEG input
- Change autonomy level (A1 micro-confirm, A2 task-confirm)
- Adjust trust thresholds
