# Test Fixes Needed

**Status:** Identified 5 critical issues causing 105 test failures

---

## Issue Summary

| # | Issue | Affected Tests | Fix Location | Severity |
|---|-------|---------------|--------------|----------|
| 1 | `last_affordance_result` → `current_affordances` | 20+ | `system_orchestrator.py` | **CRITICAL** |
| 2 | `RecoveryController.check()` missing | 15+ | `recovery_controller.py` | **CRITICAL** |
| 3 | `ActionRecord` API mismatch | 30+ | Test files | **HIGH** |
| 4 | `HandDetectionResult` missing `hand_position` | 10+ | Test files | **MEDIUM** |
| 5 | `SmartWorldSim.apply_action()` API mismatch | 5+ | Test files | **MEDIUM** |

---

## Issue 1: `last_affordance_result` → `current_affordances`

### Problem:
`SystemOrchestrator` uses `self.last_affordance_result` but attribute is actually `self.current_affordances`

### Current Code (WRONG):
```python
# In src/intent_core/system_orchestrator.py line 1486-1487
affordances_ok = (self.last_affordance_result is not None and
                 len(self.last_affordance_result.options) > 0)
```

### Should Be:
```python
affordances_ok = (self.current_affordances is not None and
                 len(self.current_affordances.options) > 0)
```

### Fix:
Replace all instances of `self.last_affordance_result` with `self.current_affordances`

---

## Issue 2: `RecoveryController.check()` Method Missing

### Problem:
Tests call `recovery_controller.check()` but actual method is `check_and_plan()`

### Current Implementation:
```python
# In src/vision/recovery_controller.py line 181
def check_and_plan(self, ...):
```

### Tests Expect:
```python
controller.check(...)
```

### Fix Option 1 (Quick):
Add alias method:
```python
def check(self, **kwargs):
    """Alias for check_and_plan() for backward compatibility"""
    return self.check_and_plan(**kwargs)
```

### Fix Option 2 (Better):
Rename method to `check()` in implementation

---

## Issue 3: `ActionRecord` API Mismatch

### Problem:
Tests use old API with `undo_window` parameter, but current API doesn't have it

### Current Signature:
```python
@dataclass
class ActionRecord:
    action_id: str
    timestamp: float
    user_id: Optional[str]
    session_id: Optional[str]  # Required even though Optional
    object_id: str
    object_label: str
    category: str
    action_type: str
    before_state: Dict
    after_state: Dict
    reversible: bool
    expires_at: float  # NOT undo_window
```

### Tests Try To Call:
```python
record = ActionRecord(
    ...
    undo_window=10.0  # ❌ DOESN'T EXIST
)
```

### Fix:
Tests need to pass `expires_at=timestamp + undo_window` instead of `undo_window=`

**Also:** `session_id` is required (even though typed as `Optional`). Tests pass `None` which is valid.

---

## Issue 4: `HandDetectionResult` Missing `hand_position`

### Problem:
Tests pass `hand_position=(320, 240)` but field doesn't exist

### Current Signature:
```python
@dataclass
class HandDetectionResult:
    landmarks: Optional[HandLandmarks]
    detected: bool
    confidence: float
    frame_id: int
    timestamp: float
    failure_reason: Optional[str] = None
    # ❌ No hand_position field
```

### Tests Try To Call:
```python
result = HandDetectionResult(
    detected=True,
    confidence=0.9,
    hand_position=(320, 240),  # ❌ DOESN'T EXIST
    failure_reason=None
)
```

### Fix Option 1 (Quick):
Add `hand_position` field to `HandDetectionResult`

### Fix Option 2 (Better):
Update tests to not pass `hand_position` (not critical for tests)

---

## Issue 5: `SmartWorldSim.apply_action()` API Mismatch

### Problem:
Tests call with keyword args, but method expects `ActionRequest` object

### Current Signature:
```python
def apply_action(self, request: ActionRequest) -> Tuple[Dict, Dict]:
```

### Tests Try To Call:
```python
world.apply_action(
    object_id="lamp_001",  # ❌ WRONG
    action_type="toggle_power"  # ❌ WRONG
)
```

### Should Be:
```python
from execution.action_schema import ActionRequest, ActionType

request = ActionRequest(
    object_id="lamp_001",
    category="lamp",
    action_type=ActionType.TOGGLE_POWER,
    timestamp=1.0
)
world.apply_action(request)
```

### Fix:
Tests need to create `ActionRequest` objects

---

## Fix Priority

### Immediate (Fix in production code):
1. **Issue 1** - Change `last_affordance_result` → `current_affordances`
2. **Issue 2** - Add `check()` alias to `RecoveryController`

### Update Later (Fix in tests):
3. **Issue 3** - Update `ActionRecord` test calls
4. **Issue 4** - Remove `hand_position` from test calls
5. **Issue 5** - Use `ActionRequest` in tests

---

## Commands to Apply Fixes

### Fix 1: Affordance Attribute Name
```bash
cd src/intent_core
sed -i '' 's/self\.last_affordance_result/self.current_affordances/g' system_orchestrator.py
```

### Fix 2: Recovery Controller Alias
Add to `RecoveryController` class:
```python
def check(self, **kwargs):
    """Alias for check_and_plan() for backward compatibility"""
    return self.check_and_plan(**kwargs)
```

---

## Estimated Impact After Fixes

**Before:**
- 160 passed
- 105 failed
- 17 skipped

**After Fixes 1-2 (estimated):**
- 200+ passed
- 60-70 failed
- 17 skipped

**After All Fixes (estimated):**
- 250+ passed
- 20-30 failed
- 17 skipped

---

**Date:** December 31, 2024  
**Analysis Complete:** Ready to apply fixes






