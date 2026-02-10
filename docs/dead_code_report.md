# Dead Code Report

Scope: requested candidates only. No files were deleted.
Method: counted direct Python importers (`import ...` / `from ... import ...`) across `*.py` in repo.

## SAFE TO DELETE

### Root-level scripts (standalone, no live imports)

| Item | Exists | Import count | Notes |
|---|---:|---:|---|
| `test_camera.py` | yes | 0 | Standalone OpenCV camera check |
| `test_camera_minimal.py` | yes | 0 | Standalone camera diagnostic |
| `test_demo_setup.py` | yes | 0 | References legacy `src/intent_core/*` paths |
| `create_demo_files.py` | yes | 0 | Copies legacy Week 9 files into another directory |
| `fix_imports.py` | yes | 0 | One-off migration utility |
| `setup_intent_demo.py` | yes | 0 | Bootstraps legacy demo layout |
| `demo_arm_intent_wk7.py` | yes | 0 | Imports legacy top-level modules (`robotics`, `world`, `intent_core`) |

### Legacy scripts (no live imports; use legacy module tree)

| Item | Exists | Import count | Notes |
|---|---:|---:|---|
| `scripts/run_unified_demo.py` | yes | 0 | Imports `intent_core`, `sim` (legacy top-level) |
| `scripts/run_unified_arm_demo.py` | yes | 0 | Imports `robotics/world/perception/intent_core/sim` |
| `scripts/run_virtual_arm_demo.py` | yes | 0 | Imports legacy top-level modules |
| `scripts/run_virtual_arm_demo_headless.py` | yes | 0 | Imports `robotics` legacy module |

### Shell wrappers for legacy scripts

| Item | Exists | Import count | Notes |
|---|---:|---:|---|
| `run_demo.sh` | yes | 0 | Shell wrapper to run `scripts/run_unified_arm_demo.py` |
| `RUN_ROBOTICS.sh` | yes | 0 | Shell wrapper to run legacy virtual arm demo |

### `scripts/` test utilities (standalone, not imported)

| Item | Exists | Import count | Notes |
|---|---:|---:|---|
| `scripts/test_camera.py` | yes | 0 | Standalone camera utility |
| `scripts/test_complete_flow.py` | yes | 0 | Legacy constructor call for `Orchestrator` |
| `scripts/test_demo_import.py` | yes | 0 | Imports legacy `robotics/world` |
| `scripts/test_keyboard.py` | yes | 0 | Standalone GUI keyboard diagnostic |
| `scripts/test_object_state.py` | yes | 0 | Imports legacy `robotics/perception` |
| `scripts/test_world_model.py` | yes | 0 | Imports legacy `robotics/world` |

### `examples/` directory

| Item | Exists | Import count | Notes |
|---|---:|---:|---|
| `examples/*.py` (5 files) | yes | 0 (all) | Not imported anywhere. They import `src.vision.*`/`src.intent_core.*` symbols that are not present in active `src/`; related legacy packages exist only under `archive/src_old_backup/` |

## MEDIUM (possibly dead, needs verification)

| Item | Import count | Notes |
|---|---:|---|
| `src/input/keyboard_input.py` | 3 | Coexists with pipeline keyboard source; likely legacy path |
| `src/input/source_keyboard.py` | 2 | Active pipeline path (factory + demo wiring) |
| `src/input/decision_filter.py` | 1 | Legacy filter path |
| `src/input/filter.py` | 7 | Active decision pipeline filter |
| `src/input/decision_source.py` | 1 | Legacy source interface |
| `src/input/source_base.py` | 5 | Active source base for pipeline |
| `src/input/eeg_source.py` | 1 | Legacy EEG wrapper |
| `src/input/eeg/eeg_source.py` | 3 | Active EEG source in new path |
| `src/input/fake_decision_source.py` | 1 | Legacy fake source |
| `src/input/source_fake.py` | 5 | Active fake source for tests/pipeline |
| `src/planning/primitive.py` | 3 | Executor currently consumes this type |
| `src/interfaces/primitive.py` | 6 | Compiler/interfaces also define primitive contract |
| `src/planning/planner.py` | 0 | No direct importers detected |
| `src/planning/preconditions.py` | 1 | Imported only by `src/planning/planner.py` |
| `src/intelligence/proposer_base.py` | 0 | No direct importers detected |
| `src/interfaces/proposer_base.py` | 5 | Active interface base in DI path |
| `src/intelligence/scene_summary.py` | 2 | Parallel to interface scene summary contract |
| `src/interfaces/scene_summary.py` | 18 | Primary shared contract in active path |
| `src/core/trust_metrics.py` | 1 | Used by orchestrator UI metrics |
| `src/core/trust.py` | 2 | Used by orchestrator trust/re-auth logic |
| `src/robot/actions.py` | 2 | Imported in a small number of places; verify runtime path |
| `src/recovery/pause_controller.py` | 0 | No direct importers detected |
| `src/recovery/recovery_plan.py` | 0 | No direct importers detected |
| `src/ui/snapshot_builder.py` | 0 | No direct importers detected |
| `src/worlds/world_artifacts.py` | 2 | Active world builder artifact type |
| `src/interfaces/world_artifacts.py` | 2 | Parallel interface artifact type |

## RISKY (probably dead but verify carefully)

| Item | Import count | Notes |
|---|---:|---|
| `src/external/gemini/types.py` | 3 | Not dead by imports. Also `src/external/gemini/` contains multiple active files (`client.py`, `parser.py`, `cache.py`, etc.), so this is not the only file in that package |

## Notes

- Import count is not the same as runtime usage frequency; scripts can be invoked directly without being imported.
- Legacy top-level modules (`robotics`, `world`, `intent_core`, `perception`, `sim`, `vision`) are present under `archive/src_old_backup/` but not in the active `src/` package structure.
