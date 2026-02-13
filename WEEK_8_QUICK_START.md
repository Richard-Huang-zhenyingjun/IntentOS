# Week 8 Quick Start Guide

## 🚀 Quick Validation

Run the Week 8 validation script to verify all components:

```bash
cd '/Users/richardhuang/Intent Interface Prototype '
python scripts/validate_week8.py
```

**Expected Output**: All components validated ✅, Safety Guarantee: PASS

---

## 🧪 Run Tests

Run all Week 8 tests (41 tests):

```bash
python -m pytest tests/test_week8_*.py -v
```

**Expected Output**: 41 passed in ~0.3s

Individual test suites:
```bash
# Recovery integration tests (12 tests)
python -m pytest tests/test_week8_recovery_integration.py -v

# Fault injection tests (13 tests)
python -m pytest tests/test_week8_fault_injection.py -v

# Undo/cancel tests (16 tests)
python -m pytest tests/test_week8_undo_cancel.py -v
```

---

## 📚 Key Components

### 1. RecoveryController

Monitor failures and trigger pauses:

```python
from src.robotics.recovery import RecoveryController
import yaml

cfg = yaml.safe_load(open('configs/robotics.yaml'))
recovery = RecoveryController(cfg['recovery'])

# Check EEG stability (30 frame grace period)
if not recovery.check_eeg_stable(is_stable):
    print(f"PAUSED: {recovery.get_status().explanation}")

# Check target visibility (10 frame grace period)
if not recovery.check_target_visible(target_visible):
    print(f"PAUSED: {recovery.get_status().explanation}")

# After user re-engages
recovery.reset()
```

### 2. FaultInjector

Deterministic fault injection for testing:

```python
from src.robotics.recovery import FaultInjector, FaultType

fi = FaultInjector({'enabled': True, 'seed': 42, 'schedule': []})

# Schedule faults
fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=100, duration_frames=30)
fi.schedule_fault(FaultType.TARGET_LOST, trigger_frame=200, duration_frames=50)

# In control loop
fi.tick(current_frame)
if fi.should_inject_eeg_dropout():
    # Simulate dropout
    pass
```

### 3. TrustMetricsTracker

Track safety guarantees:

```python
from src.robotics.recovery import TrustMetricsTracker, PauseTrigger

tracker = TrustMetricsTracker()

# Record events
tracker.record_execution("MOVE_ARM_UP", confirmed=True, success=True)
tracker.record_pause(PauseTrigger.EEG_UNSTABLE, "EEG unstable")
tracker.record_recovery()

# Generate report
report = tracker.generate_report()
tracker.print_summary()

# Verify safety guarantee
assert report.false_executions == 0, "Safety violation!"
```

### 4. UndoController

Return to rest pose:

```python
from src.robotics.recovery import UndoController

uc = UndoController(cfg['recovery'])

# Start return to rest (detaches object if holding)
uc.start_return_to_rest(sim, grasp_logic)

# Execute in control loop
while uc.is_active():
    done, result = uc.tick(sim)
    if done:
        print(f"Return to rest: {result.reason}")
        break
```

---

## 📊 Configuration

Edit `configs/robotics.yaml` to customize recovery behavior:

```yaml
recovery:
  enable: true
  
  # Pause triggers
  pause_on:
    eeg_unstable: true
    target_lost: true
    action_timeout: true
  
  # Grace periods (frames before pause)
  target_loss_grace_frames: 10    # ~0.3s at 30fps
  eeg_unstable_grace_frames: 30   # ~1.0s at 30fps
  
  # Rest pose
  rest_pose:
    enabled: true
    joint_positions: []  # Empty = use current pose
  
  # Undo
  undo:
    enable_return_to_rest: true
    detach_before_rest: true

# Fault injection (for testing)
faults:
  enabled: false  # Enable via --faults flag
  seed: 42
  schedule: []
```

---

## 🎯 Safety Guarantees

Week 8 enforces these safety guarantees:

1. **No False Executions**: `false_executions = 0` (never execute without confirmation)
2. **Pause on Failure**: Always pause when failure detected
3. **Transparent Refusals**: Every pause has clear explanation
4. **No Auto-Resume**: User must explicitly re-engage

Verify with:
```python
report = tracker.generate_report()
assert report.false_executions == 0
assert report.all_refusals_explained
```

---

## 📖 Documentation

- **Full Documentation**: `WEEK_8_COMPLETE.md`
- **Configuration**: `configs/robotics.yaml`
- **Tests**: `tests/test_week8_*.py`
- **Source**: `src/robotics/recovery/`

---

## ✅ Verification Checklist

- [ ] Run validation script: `python scripts/validate_week8.py`
- [ ] Run all tests: `python -m pytest tests/test_week8_*.py -v`
- [ ] Check configuration: `configs/robotics.yaml` has recovery section
- [ ] Verify imports: `from src.robotics.recovery import RecoveryController`
- [ ] Review documentation: `WEEK_8_COMPLETE.md`

---

## 🎉 Week 8 Complete!

All core safety and recovery features implemented and tested:
- ✅ RecoveryController with grace periods
- ✅ PAUSED/RECOVERING state machine
- ✅ Undo/return-to-rest functionality
- ✅ Fault injection for testing
- ✅ Trust metrics for safety guarantees
- ✅ 41/41 tests passing

**Safety Philosophy**: Pause > partial execution, every refusal explained, no auto-resume.






