# Crash Hypothesis Analysis Report
**Date:** 2025-01-07  
**Purpose:** Investigate three hypotheses for L key crash after multiple presses

---

## Hypothesis #1: `safe_debug_text()` Fails, Accumulates Errors

### Status: ✅ **INVESTIGATED - LOGGING ADDED**

### Evidence:
- "Press L 3-5 times → crash"
- Each press calls `safe_debug_text()` twice (error case + success case)
- If `addUserDebugText()` fails internally, it might accumulate state

### Current Implementation:
```python
# src/utils/safe_pybullet.py:104-139
def safe_add_debug_text(...):
    # Validate parent body if provided
    if parent_body_id is not None and not self.is_valid_body(parent_body_id):
        parent_body_id = None  # Degrade to world-space text
    
    try:
        return p.addUserDebugText(...)
    except Exception as e:
        print(f"[SAFE_PB] ⚠️ Failed to add debug text: {e}")
        return None
```

### Changes Made:
✅ **Added detailed debug logging** to track every call:
```python
print(f"[SAFE_PB DEBUG] Attempting to add text: '{text}'")
print(f"[SAFE_PB DEBUG] Position: {position}, Parent: {parent_body_id}, Replace: {replace_id}")
# ... after call ...
print(f"[SAFE_PB DEBUG] Success, ID: {result}")
# ... on exception ...
print(f"[SAFE_PB DEBUG] FAILED: {e}")
traceback.print_exc()
```

### Analysis:
- **Error handling:** ✅ Exceptions are caught and logged
- **Return value:** Returns `None` on failure (safe)
- **State accumulation:** No internal state is stored, so failures shouldn't accumulate
- **Potential issue:** If `replace_id` is invalid, PyBullet might fail silently or accumulate stale items

### Verification Steps:
1. Run demo and press L key 5 times rapidly
2. Check console for `[SAFE_PB DEBUG]` messages
3. Look for patterns:
   - Does it fail on first press or later?
   - Are `replace_id` values valid?
   - Does PyBullet return valid IDs?

---

## Hypothesis #2: `force_lock_target()` Succeeds But Rendering Fails Later

### Status: ✅ **INVESTIGATED - NO RAW CALLS FOUND**

### Timeline:
```
Press L → force_lock_target() called → _pending_forced_lock set → returns
Frame processes → apply lock → selector.force_lock() called
Rendering → try to draw lock indicator → CRASH
```

### What `draw_lock_indicator()` Actually Does:

**File:** `src/ui/selection_overlay.py:86-123`

```python
def draw_lock_indicator(self, pose: Optional[Tuple[List[float], List[float]]]) -> None:
    # Clear hover indicator when showing lock
    if self.hover_indicator_id is not None:
        try:
            p.removeUserDebugItem(self.hover_indicator_id)  # ⚠️ RAW CALL
        except:
            pass
        self.hover_indicator_id = None
    
    if pose is None:
        # Clear lock indicator if no object
        if self.lock_indicator_id is not None:
            try:
                p.removeUserDebugItem(self.lock_indicator_id)  # ⚠️ RAW CALL
            except:
                pass
            self.lock_indicator_id = None
        return
    
    # Render using validated pose (no PyBullet calls with IDs)
    pos, _ = pose
    text_pos = [pos[0], pos[1], pos[2] + 0.15]
    
    # STEP B: Use safe debug text wrapper
    self.lock_indicator_id = safe_debug_text(
        text="🔒 LOCKED TARGET",
        position=text_pos,
        color=(0.0, 1.0, 0.0),  # Green
        size=1.5,
        lifetime=0,
        replace_id=self.lock_indicator_id
    )
```

### Analysis:

**✅ Safe aspects:**
- Receives **validated pose** (not body ID)
- Uses `safe_debug_text()` for text rendering
- No `p.getBasePositionAndOrientation()` calls
- No body ID operations

**⚠️ Potential issues:**
- **`p.removeUserDebugItem()` calls:** 5 raw calls found (lines 34, 54, 63, 96, 105)
- **Error handling:** All wrapped in `try-except: pass` (safe but silent)
- **Invalid `replace_id`:** If `self.lock_indicator_id` is stale, `safe_debug_text()` might fail

### Raw PyBullet Calls Found:

| File | Line | Call | Wrapped? | Risk |
|------|------|------|----------|------|
| `selection_overlay.py` | 34 | `p.removeUserDebugItem()` | ✅ try-except | LOW |
| `selection_overlay.py` | 54 | `p.removeUserDebugItem()` | ✅ try-except | LOW |
| `selection_overlay.py` | 63 | `p.removeUserDebugItem()` | ✅ try-except | LOW |
| `selection_overlay.py` | 96 | `p.removeUserDebugItem()` | ✅ try-except | LOW |
| `selection_overlay.py` | 105 | `p.removeUserDebugItem()` | ✅ try-except | LOW |

**Note:** `removeUserDebugItem()` doesn't take body IDs, so it's safe. However, if the item ID is invalid, it might fail silently.

### Verification:
- ✅ No `p.getBasePositionAndOrientation()` in rendering path
- ✅ No body ID operations in `draw_lock_indicator()`
- ⚠️ Raw `removeUserDebugItem()` calls exist but are wrapped

---

## Hypothesis #3: Multiple ArmSimulator Instances

### Status: ✅ **VERIFIED - SINGLE INSTANCE**

### Evidence from Report:
> "If multiple ArmSimulator instances exist, each would call init_safe_pybullet() with its own client ID, overwriting the global instance"

### Search Results:

**`ArmSimulator` creation in `run_unified_arm_demo.py`:**
```python
# Line 155: Single creation before main loop
sim = ArmSimulator(temp_cfg_path)
sim.connect()
sim.reset_world()
```

**All `ArmSimulator()` calls found:**
| File | Line | Context |
|------|------|---------|
| `run_unified_arm_demo.py` | 155 | ✅ Single instance before loop |
| `run_virtual_arm_demo.py` | 171 | Different script |
| `test_demo_import.py` | 25 | Test file |
| `test_world_model.py` | 33 | Test file |
| `test_object_state.py` | 29 | Test file |
| `run_virtual_arm_demo_headless.py` | 62 | Different script |

### Analysis:

**✅ Safe:**
- `run_unified_arm_demo.py` creates **exactly ONE** `ArmSimulator` instance
- Created **before** main loop starts (line 155)
- Never recreated during runtime
- No error recovery that recreates simulator

**✅ `init_safe_pybullet()` called once:**
```python
# src/robotics/arm_simulator.py:100
init_safe_pybullet(physics_client_id=self.physics_client)
```
- Called in `connect()` method
- `connect()` is called once (line 156)
- Guarded by `_connected` flag (line 69-71)

### Potential Issue (Low Risk):

**`init_safe_pybullet()` can be overwritten:**
```python
# src/utils/safe_pybullet.py:181-184
def init_safe_pybullet(physics_client_id: int = 0):
    global _safe_pb
    _safe_pb = SafePyBullet(physics_client_id)  # No guard
```

**Risk:** If somehow `connect()` is called twice, the global instance would be overwritten. However, `connect()` is guarded, so this shouldn't happen.

### Verification:
- ✅ Single `ArmSimulator` instance
- ✅ `init_safe_pybullet()` called once
- ✅ `connect()` guarded against multiple calls
- ⚠️ No guard in `init_safe_pybullet()` itself (low risk)

---

## Summary & Recommendations

### Hypothesis #1: `safe_debug_text()` Failures
- **Status:** ✅ Logging added, ready for testing
- **Risk:** MEDIUM - Failures could accumulate if `replace_id` handling is flawed
- **Action:** Monitor debug output during crash

### Hypothesis #2: Rendering Failures
- **Status:** ✅ Investigated, no critical issues found
- **Risk:** LOW - All calls are wrapped or safe
- **Action:** Monitor `removeUserDebugItem()` failures (currently silent)

### Hypothesis #3: Multiple Instances
- **Status:** ✅ Verified single instance
- **Risk:** LOW - No multiple instances found
- **Action:** None needed

### Next Steps:

1. **Run test with debug logging:**
   ```bash
   python scripts/run_unified_arm_demo.py --mode happy_path --eeg --no-gaze
   # Press L key 5 times rapidly
   # Check console for [SAFE_PB DEBUG] messages
   ```

2. **Check for patterns:**
   - Does crash occur on first press or later?
   - Are there `[SAFE_PB DEBUG] FAILED` messages?
   - What are the `replace_id` values?

3. **If Hypothesis #1 confirmed:**
   - Add validation for `replace_id` before passing to PyBullet
   - Consider clearing stale debug item IDs

4. **If Hypothesis #2 confirmed:**
   - Wrap `removeUserDebugItem()` in safe wrapper
   - Add logging to track failures

5. **If Hypothesis #3 confirmed:**
   - Add guard to `init_safe_pybullet()` to prevent overwriting
   - Add logging when instance is overwritten

---

## Debug Output Format

When running with debug logging, expect output like:
```
[SAFE_PB DEBUG] Attempting to add text: '✅ Lock queued: cube 2'
[SAFE_PB DEBUG] Position: (0.5, 0.0, 1.0), Parent: None, Replace: None
[SAFE_PB DEBUG] Success, ID: 12345

[SAFE_PB DEBUG] Attempting to add text: '✅ Lock queued: cube 2'
[SAFE_PB DEBUG] Position: (0.5, 0.0, 1.0), Parent: None, Replace: 12345
[SAFE_PB DEBUG] Success, ID: 12345
```

If failures occur:
```
[SAFE_PB DEBUG] Attempting to add text: '✅ Lock queued: cube 2'
[SAFE_PB DEBUG] Position: (0.5, 0.0, 1.0), Parent: None, Replace: 99999
[SAFE_PB DEBUG] FAILED: <exception details>
Traceback (most recent call last):
  ...
```



