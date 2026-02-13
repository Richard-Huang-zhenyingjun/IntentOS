# Week 5: Decision Pipeline + Quality Gating Report
Date: [Fill in]

## Objective
Refactor input layer into Source → Router → Filter pipeline
so Week 6 EEG integration requires only one new file.

## Architecture

### Pipeline Stages
1. **Sources**: Raw input readers (keyboard, mock EEG)
2. **Router**: Policy-driven source selection (4 modes)
3. **Filter**: Quality gate + debounce + hold-to-confirm
4. **Output**: Single DecisionFrame to orchestrator

### Routing Modes
| Mode | Behavior | Use Case |
|------|----------|----------|
| KEYBOARD_ONLY | Only keyboard | Default, Week 0-4 compat |
| EEG_ONLY | Only EEG | Testing EEG in isolation |
| ANY | First confirm wins | Flexible multi-input |
| DUAL | Both must confirm | Production BCI safety |

### Filter Stages
1. Quality gate: quality < 0.65 → blocked
2. Debounce: 6 frames between confirms
3. Hold-to-confirm: N consecutive frames required

### Safety Invariants
- CANCEL always passes (never gated)
- Filter can only REDUCE confirms, never CREATE
- NONE input → NONE output (always)

## Test Results
```
✅ Filter tests: 10/10 PASSED
✅ Router tests: 7/7 PASSED  
✅ Dual confirm: 3/3 PASSED
✅ No false confirm (1000 frames × 3 modes): 3/3 PASSED
✅ All Week 0-4 regression: 54/54 PASSED
✅ false_executions == 0: PRESERVED
```

**Detailed Breakdown:**
- `test_decision_filter.py`: 10/10 PASSED
  - Quality gate (5 tests)
  - Debounce (2 tests)
  - Hold-to-confirm (2 tests)
  - None passthrough (1 test)

- `test_decision_router.py`: 7/7 PASSED
  - KEYBOARD_ONLY mode (2 tests)
  - ANY mode (2 tests)
  - Cancel priority (1 test)
  - No false confirm (2 tests)

- `test_dual_confirm_window.py`: 3/3 PASSED
  - Both confirm within window
  - Only one source confirms
  - Outside window rejection

- `test_no_false_confirm.py`: 3/3 PASSED
  - ANY mode (1000 frames)
  - KEYBOARD_ONLY mode (1000 frames)
  - DUAL mode (1000 frames)

## How to Add Real EEG (Week 6 Guide)

1. Create `src/input/source_brainlink.py`
   - Implement `DecisionSourceBase`
   - Read from BrainLink hardware
   - Report quality from MNE preprocessing
2. In config: `sources_enabled: ["keyboard", "eeg"]`
3. In factory: register new source
4. That's it. Router, filter, orchestrator unchanged.

## Definition of Done ✅
- ✅ DecisionFrame replaces Week 3 Decision
- ✅ Router supports 4 modes (config-driven)
- ✅ Filter: debounce + hold + quality gate
- ✅ CANCEL always passes
- ✅ No false confirms (invariant tested)
- ✅ Mock EEG exercises quality gate
- ✅ Pipeline injectable (DI via factory)
- ✅ Zero regression

---

## Week 5 Definition of Done Checklist
```
Filter:
✅ test_decision_filter.py → 10/10 PASSED

Router:
✅ test_decision_router.py → 7/7 PASSED

Dual Mode:
✅ test_dual_confirm_window.py → 3/3 PASSED

Safety Invariant:
✅ test_no_false_confirm.py → 3/3 PASSED (3000 frames total)

Regression (Week 0-4):
✅ All previous tests PASSED (54/54)
✅ false_executions == 0 preserved

Visual Demo (identical to Week 4):
✅ python scripts/run_demo.py → same behavior as before
✅ Keyboard L → C → cleaning works

Code Quality:
✅ Pipeline stages are independently testable
✅ No external imports in pipeline code
✅ Config-driven mode switching
✅ Mock EEG provides realistic test scenarios
```

## Key Files Created

**Decision Pipeline Types:**
- `src/input/types.py` - DecisionFrame, DecisionIntent, SourceType, FilterAction, RawSourceReading

**Sources:**
- `src/input/source_base.py` - DecisionSourceBase (ABC)
- `src/input/source_keyboard.py` - KeyboardSource (migrated)
- `src/input/source_eeg_mock.py` - MockEEGSource
- `src/input/source_fake.py` - FakeSource (for tests)

**Pipeline Components:**
- `src/input/policies.py` - DecisionPolicy, RoutingMode
- `src/input/router.py` - DecisionRouter
- `src/input/filter.py` - DecisionFilter
- `src/input/pipeline.py` - DecisionPipeline (assembled)

**Tests:**
- `tests/test_decision_filter.py` - 10 filter tests
- `tests/test_decision_router.py` - 7 router tests
- `tests/test_dual_confirm_window.py` - 3 dual mode tests
- `tests/test_no_false_confirm.py` - 3 invariant tests

**Configuration:**
- `configs/default.yaml` - Updated with Week 5 input pipeline config

## Configuration Example

```yaml
input:
  mode: "KEYBOARD_ONLY"          # KEYBOARD_ONLY | EEG_ONLY | ANY | DUAL
  sources_enabled: ["keyboard"]   # Week 6 adds "eeg"
  debounce_frames: 6
  confirm_hold_frames: 1
  min_quality: 0.65
  dual:
    sources: ["keyboard", "eeg"]
    window_ms: 900

keyboard:
  confirm_key: "c"
  cancel_key: "x"
  lock_key: "l"

eeg_mock:
  enabled: false
  confirm_probability: 0.02
  quality_mean: 0.5
  quality_std: 0.15
  artifact_probability: 0.05
  seed: null
```

## Lessons Learned

1. **Pipeline Architecture**: Separating sources, routing, and filtering makes each stage independently testable and easier to reason about
2. **Safety Invariants**: Explicit testing of "no false confirms" ensures the pipeline never creates execution signals
3. **Config-Driven Design**: Routing modes are config-driven, making it easy to switch between keyboard-only, EEG-only, dual-confirm, etc.
4. **Mock Sources**: MockEEGSource enables testing quality gating without hardware
5. **Frozen Types**: DecisionFrame being frozen prevents accidental mutation mid-pipeline

## Next Steps

1. **Week 6**: Add real BrainLink EEG source
2. **Week 6**: MNE preprocessing integration for quality estimation
3. **Week 6**: Update config to enable EEG in production
4. **Future**: Add more routing policies (e.g., weighted voting)



