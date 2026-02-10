# Intent Interface - Simplified

**Philosophy**: SELECT → PROPOSE → CONFIRM → EXECUTE  
**Safety**: `false_executions == 0`

## Quick Start

- Demo quick start: `README_DEMO.md`
- Run command: `python scripts/run_demo.py --seed 42`
- Full setup dependencies: `requirements.txt`

## Architecture Overview

- System architecture: `docs/ARCHITECTURE.md`
- Execution/root-cause project summary: `ROBOTIC_ARM_MOVEMENT_ANALYSIS.md`
- Frozen contracts: `docs/frozen_interfaces.md`

## Safety Guarantees

- **Invariant:** `false_executions == 0` (no primitive execution without valid authorization token)
- **Execution gate:** orchestration checks authorization before execution tick
- **Tier boundaries:**
  - `src/interfaces/*` are contract-only and self-contained
  - `src/core/*` does not directly import external AI/EEG providers
  - composition wiring stays in `src/core/system_factory.py`

## Development Workflow

1. Install dependencies: `pip install -r requirements.txt`
2. Run full test suite: `pytest tests/ -v`
3. Run focused tests while iterating: `pytest tests/test_<module>.py -v`
4. Run demo: `python scripts/run_demo.py --seed 42`
5. Replay events: `python -m src.tools.replay_events demo_artifacts/demo_run_seed42_events.jsonl`

## Known Limitations

- PyBullet behavior can vary by platform/build; deterministic seeds do not guarantee identical contact physics across machines.
- Gemini integrations may incur network/API cost and latency when enabled.
- Real EEG path depends on compatible hardware/runtime availability and can fall back to keyboard when unavailable.
- Current demo reliability still depends on test-local shims for some stress/fault scenarios until runtime execution path parity is fully unified.

## Current Status: Week 2 Complete ✅

### Capabilities
- ✅ **Week 0**: Deterministic arm motion
- ✅ **Week 1**: Single-object CLEAN_TABLE with intent loop
- ✅ **Week 2**: Multi-object cleaning with recovery + timeouts

### Week 2 Demo
```bash
conda activate intent_interface
python scripts/run_demo.py
```

**What to expect:**
1. Messy table with 6 objects
2. Press `L` → System proposes "CLEAN_TABLE (6 objects)"
3. Press `C` → Arm cleans multiple objects sequentially
4. Automatically skips unreachable objects
5. Retries failed grasps once
6. Completes when all reachable objects in bin

**New in Week 2:**
- Multi-object loop (cleans 3-6 objects per session)
- Recovery behaviors (skip unreachable, retry grasp)
- Timeout protection (3sec per primitive, 12sec per object)
- Structured logging (`runs/TIMESTAMP/events.jsonl`)
- Enhanced overlay (shows task progress, retries, errors)

### Tests
```bash
# Week 2 tests
pytest tests/test_clean_table_multi_object.py -v -s
pytest tests/test_recovery_skip_unreachable.py -v -s
pytest tests/test_timeout_abort_safe.py -v -s

# Full regression
pytest tests/ -v
```

### Architecture (Week 2)
```
TaskExecutor (multi-object loop)
    ↓
PlanCompiler (validate + generate 8 primitives)
    ↓
PrimitiveExecutor (timeout + error codes)
    ↓
Controller (multi-frame motion)
```

### Next: Week 3
- Strict tier boundaries (prepare for Gemini)
- Interface contracts (lock schemas)
- Proposer fallback testing

---

## Quick Start

```bash
python scripts/run_demo.py
```

## Structure

```
src/
├── core/          # Orchestrator, state machine, trust metrics, events (Week 2)
├── input/         # Keyboard + EEG decision sources
├── robot/         # Simulator, controller, grasp, actions
├── planning/      # Action preconditions + planner + plan compiler (Week 1)
├── recovery/      # Pause controller
├── ui/            # Debug overlay (enhanced Week 2)
├── intelligence/   # Scene summary + heuristic proposer (Week 1)
├── execution/     # Primitive executor + task executor (Week 1-2)
└── worlds/        # World builders (Week 1)

scripts/
└── run_demo.py    # Single demo entrypoint

configs/
└── default.yaml   # Configuration

docs/
├── week1_clean_table_report.md  # Week 1 completion report
└── week2_robust_cleaning_report.md  # Week 2 completion report

runs/
└── TIMESTAMP/
    └── events.jsonl  # Structured event logs (Week 2)
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
# Run all tests
pytest tests/ -v

# Week 2 tests
pytest tests/test_clean_table_multi_object.py -v -s
pytest tests/test_recovery_skip_unreachable.py -v -s
pytest tests/test_timeout_abort_safe.py -v -s

# Week 1 tests
pytest tests/test_proposer_heuristic.py -v
pytest tests/test_plan_compiler.py -v
pytest tests/test_primitive_executor.py -v
pytest tests/test_clean_table_integration.py -v -s
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

## Week 2 Definition of Done ✅

### Visual Demo Checklist
- ✅ Run `scripts/run_demo.py`
- ✅ Table with 6 objects
- ✅ Press L → Proposal shows "6 objects"
- ✅ Press C → State: EXECUTING
- ✅ Overlay shows "Objects: 1 cleaned..." → "2 cleaned..." → etc.
- ✅ Watch arm clean multiple objects sequentially
- ✅ State transitions to DONE after all objects processed
- ✅ Check `runs/TIMESTAMP/events.jsonl` exists

### Unit/Integration Tests
- ✅ `pytest tests/test_clean_table_multi_object.py -v -s` → PASSED (3+ objects in bin)
- ✅ `pytest tests/test_recovery_skip_unreachable.py -v -s` → PASSED (skip + clean others)
- ✅ `pytest tests/test_timeout_abort_safe.py -v -s` → PASSED (no hang)

### Regression Tests (Week 0/1 still work)
- ✅ `pytest tests/test_arm_moves_basic.py -v` → PASSED
- ✅ `python scripts/run_motion_baseline.py` → SUCCESS

### Code Quality
- ✅ Error codes used consistently
- ✅ Events emitted at key milestones
- ✅ Task/Primitive separation clear
- ✅ Config-driven timeouts
- ✅ Deterministic (seeded)

### Documentation
- ✅ `docs/week2_robust_cleaning_report.md` complete
- ✅ `README.md` updated with Week 2 status
- ✅ Code has docstrings

### Invariant Preservation
- ✅ `false_executions == 0` in all tests
- ✅ One confirm authorizes multi-object session
- ✅ Trust metrics logged correctly

## Refactoring

This codebase was refactored from 110+ files to 25 core files (~77% reduction) while maintaining all critical functionality. The old structure is archived in `archive/` for reference.
