# Intent Interface - Simplified

**Philosophy**: SELECT → PROPOSE → CONFIRM → EXECUTE  
**Safety**: `false_executions == 0`

## Quick Start

```bash
python scripts/run_demo.py
```

## Structure

```
src/
├── core/          # Orchestrator, state machine, trust metrics
├── input/         # Keyboard + EEG decision sources
├── robot/         # Simulator, controller, grasp, actions
├── planning/      # Action preconditions + planner
├── recovery/      # Pause controller
└── ui/            # Debug overlay

scripts/
└── run_demo.py    # Single demo entrypoint

configs/
└── default.yaml   # Configuration
```

## Controls

- **L**: Lock target
- **C**: Confirm action
- **X**: Cancel
- **R**: Reset
- **Q**: Quit

## Core Guarantee

**`false_executions == 0`**  
No execution without explicit confirmation.

## Tests

```bash
pytest tests/ -v
```

## Architecture

The system follows a clean, modular architecture:

- **Core**: Central orchestrator coordinates all subsystems
- **Input**: Unified decision source interface (keyboard or EEG)
- **Robot**: PyBullet simulation and control
- **Planning**: Deterministic action planning with preconditions
- **Recovery**: Pause/resume safety mechanisms
- **UI**: Minimal debug overlay

## Configuration

Edit `configs/default.yaml` to adjust:
- Robot parameters (velocity, thresholds)
- Input settings (keyboard debounce, EEG parameters)
- Recovery behavior
- UI display options

## Demo Options

```bash
# Basic keyboard demo
python scripts/run_demo.py

# EEG demo (mocked)
python scripts/run_demo.py --eeg

# Headless mode (no GUI)
python scripts/run_demo.py --headless

# Custom config
python scripts/run_demo.py --config configs/custom.yaml
```

## Refactoring

This codebase was refactored from 110+ files to 25 core files (~77% reduction) while maintaining all critical functionality. The old structure is archived in `archive/` for reference.
