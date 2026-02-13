# Keyboard Input Issue Report
**Date:** January 29, 2025  
**Issues:** L key doesn't lock target, C key doesn't confirm action

---

## Executive Summary

Two keyboard input issues identified:
1. **L key (Lock target)**: May not work due to PyBullet GUI focus requirements or keyboard buffer clearing
2. **C key (Confirm)**: Only works when state machine is in `CONFIRMING` state - requires a proposal to exist first

---

## Issue 1: L Key Doesn't Lock Target

### Code Flow

**Location:** `scripts/run_demo.py:88-90`
```python
# Handle L - Lock target
if ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED:
    orch.force_lock_target(sim.cube_id)
```

**Implementation:** `src/core/orchestrator.py:266-270`
```python
def force_lock_target(self, object_id: int):
    """Manually lock target (L key)."""
    if self.sim.is_valid_object(object_id):
        self.state_machine.set_target(object_id, locked=True)
        print(f"[ORCH] Forced lock: {object_id}")
```

### Potential Issues

#### 1. **PyBullet GUI Focus Requirement** ⚠️ **MOST LIKELY**
- **Problem:** PyBullet only captures keyboard events when the GUI window is focused
- **Symptom:** Pressing L does nothing, no console output
- **Solution:** Click on the PyBullet GUI window before pressing keys

#### 2. **Keyboard Buffer Cleared Too Early** ⚠️ **POSSIBLE**
- **Problem:** `p.getKeyboardEvents()` clears the buffer after reading
- **Current order:**
  1. `orch.step()` → `KeyboardInput.read_decision()` → reads C/X (clears buffer)
  2. Demo script reads L/R/Q
- **Issue:** If C/X keys were pressed, they consume the buffer first
- **Status:** This is actually correct - C/X have priority (as designed)

#### 3. **Invalid cube_id** ⚠️ **LESS LIKELY**
- **Problem:** `sim.cube_id` might be `None` or invalid
- **Check:** `sim.is_valid_object()` should catch this
- **Debug:** Add print statement to verify `cube_id` value

#### 4. **Case Sensitivity** ⚠️ **POSSIBLE**
- **Problem:** `ord('l')` only matches lowercase 'l'
- **Current code:** Only checks lowercase
- **Fix:** Check both `ord('l')` and `ord('L')`

### Diagnostic Steps

1. **Verify GUI focus:**
   ```python
   # Add to run_demo.py after sim creation
   print(f"[DEBUG] Cube ID: {sim.cube_id}")
   print(f"[DEBUG] Cube valid: {sim.is_valid_object(sim.cube_id)}")
   ```

2. **Add debug output:**
   ```python
   # In run_demo.py, before L key check
   if keys:  # If any keys detected
       print(f"[DEBUG] Keys detected: {list(keys.keys())}")
   ```

3. **Test keyboard capture:**
   ```python
   # Press any key - if nothing prints, GUI isn't focused
   keys = p.getKeyboardEvents()
   if keys:
       print(f"[DEBUG] Keyboard events captured: {keys}")
   ```

---

## Issue 2: C Key Doesn't Confirm

### Code Flow

**Location:** `src/input/keyboard_input.py:22-46`
```python
def read_decision(self) -> ArmDecision:
    keys = p.getKeyboardEvents()  # Reads C/X
    
    if self.CONFIRM_KEY in keys:  # ord('c')
        if key_state & p.KEY_WAS_TRIGGERED:
            if now - self.last_confirm_time > self.debounce_time:
                return ArmDecision(signal=DecisionSignal.CONFIRM, ...)
```

**Processing:** `src/core/orchestrator.py:128-136`
```python
elif state == 'confirming':
    if decision.signal == DecisionSignal.CONFIRM:
        allowed = self.state_machine.process_decision(decision)
        if allowed:
            return f"✓ Confirmed: {self.state_machine.proposal.action.value}"
```

**State Machine Check:** `src/core/state_machine.py:60-72`
```python
def process_decision(self, decision: ArmDecision) -> bool:
    if self.state != ArmUIState.CONFIRMING:  # ⚠️ CRITICAL CHECK
        return False  # C key ignored if not in CONFIRMING state
    
    if decision.signal == DecisionSignal.CONFIRM:
        self._transition_to(ArmUIState.EXECUTING)
        return True
```

### Root Cause Analysis

#### **C Key Only Works in CONFIRMING State** ✅ **BY DESIGN**

The C key confirmation requires:
1. ✅ Target must be locked (L key or automatic)
2. ✅ State machine must transition: `IDLE` → `SELECTING` → `CONFIRMING`
3. ✅ An action proposal must exist
4. ✅ State must be `CONFIRMING` (not `IDLE`, `SELECTING`, or `EXECUTING`)

**State Machine Flow:**
```
IDLE → (L pressed) → SELECTING → (action proposed) → CONFIRMING → (C pressed) → EXECUTING
```

### Why C Doesn't Work

#### **Scenario 1: No Target Locked** ⚠️ **COMMON**
- **State:** `IDLE`
- **Problem:** L key wasn't pressed or didn't work
- **Symptom:** Pressing C does nothing
- **Fix:** Press L first to lock target

#### **Scenario 2: No Proposal Yet** ⚠️ **COMMON**
- **State:** `SELECTING` (target locked, but no action proposed yet)
- **Problem:** Planner hasn't proposed an action yet
- **Symptom:** C key pressed but state is `SELECTING`, not `CONFIRMING`
- **Fix:** Wait for proposal (should happen automatically in next frame)

#### **Scenario 3: GUI Not Focused** ⚠️ **COMMON**
- **Problem:** PyBullet GUI window not focused
- **Symptom:** No keyboard events captured
- **Fix:** Click on PyBullet window

#### **Scenario 4: Debounce Too Long** ⚠️ **POSSIBLE**
- **Problem:** `debounce_time = 0.3` seconds (300ms)
- **Symptom:** Rapid C presses ignored
- **Fix:** Reduce debounce time or wait longer between presses

#### **Scenario 5: Keyboard Buffer Cleared** ⚠️ **LESS LIKELY**
- **Problem:** C key read by `KeyboardInput.read_decision()` but state not `CONFIRMING`
- **Symptom:** `[KEYBOARD] ✓ CONFIRM pressed` prints but nothing happens
- **Fix:** Ensure state machine is in `CONFIRMING` state before pressing C

### Diagnostic Steps

1. **Check current state:**
   ```python
   # Add to run_demo.py main loop
   print(f"[DEBUG] State: {snapshot.state.value}")
   print(f"[DEBUG] Proposal: {snapshot.proposal}")
   print(f"[DEBUG] Target locked: {snapshot.target_locked}")
   ```

2. **Verify C key detection:**
   ```python
   # Should print when C pressed
   # Look for: [KEYBOARD] ✓ CONFIRM pressed
   ```

3. **Check state transitions:**
   ```python
   # Should see: [FSM] idle → selecting → confirming
   ```

---

## Complete Workflow for C Key to Work

### Step-by-Step Process

1. **Start demo:**
   ```bash
   python scripts/run_demo.py
   ```

2. **Focus PyBullet GUI:**
   - Click on the PyBullet window
   - Ensure it's the active window

3. **Lock target (L key):**
   - Press `L` (lowercase)
   - Expected output: `[ORCH] Forced lock: <cube_id>`
   - Expected state: `IDLE` → `SELECTING`

4. **Wait for proposal:**
   - System automatically proposes next action
   - Expected output: `[FSM] Proposed: <action> - <reason>`
   - Expected state: `SELECTING` → `CONFIRMING`

5. **Confirm (C key):**
   - Press `C` (lowercase)
   - Expected output: `[KEYBOARD] ✓ CONFIRM pressed`
   - Expected output: `[FSM] ✓ Confirmed via keyboard`
   - Expected state: `CONFIRMING` → `EXECUTING`

---

## Recommended Fixes

### Fix 1: Improve L Key Handling

**File:** `scripts/run_demo.py`

```python
# Handle L - Lock target (case-insensitive)
if (ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED) or \
   (ord('L') in keys and keys[ord('L')] & p.KEY_WAS_TRIGGERED):
    cube_id = sim.cube_id
    if cube_id is not None:
        print(f"[DEMO] L key pressed, locking cube {cube_id}")
        orch.force_lock_target(cube_id)
    else:
        print("[DEMO] ⚠️ No cube to lock!")
```

### Fix 2: Add Debug Output for C Key

**File:** `src/core/orchestrator.py`

```python
# CONFIRMING: Awaiting decision
elif state == 'confirming':
    if decision.signal == DecisionSignal.CONFIRM:
        print(f"[ORCH] C key detected in CONFIRMING state")
        # ... rest of code
    else:
        print(f"[ORCH] Waiting for confirmation (current decision: {decision.signal})")
```

### Fix 3: Add State Debugging

**File:** `scripts/run_demo.py`

```python
# Add after snapshot = orch.step()
if snapshot.proposal:
    print(f"[DEMO] State: {snapshot.state.value}, Proposal: {snapshot.proposal.action.value}")
else:
    print(f"[DEMO] State: {snapshot.state.value}, No proposal yet")
```

### Fix 4: Reduce Debounce Time

**File:** `configs/default.yaml`

```yaml
input:
  debounce_seconds: 0.1  # Reduced from 0.3
```

---

## Testing Checklist

- [ ] PyBullet GUI window is focused
- [ ] Press L → See `[ORCH] Forced lock: <id>`
- [ ] State transitions: `idle` → `selecting`
- [ ] Wait 1-2 frames → See `[FSM] Proposed: <action>`
- [ ] State transitions: `selecting` → `confirming`
- [ ] Press C → See `[KEYBOARD] ✓ CONFIRM pressed`
- [ ] See `[FSM] ✓ Confirmed via keyboard`
- [ ] State transitions: `confirming` → `executing`

---

## Summary

| Issue | Root Cause | Solution |
|-------|------------|----------|
| **L doesn't lock** | GUI not focused OR case sensitivity | Focus GUI, check both 'l' and 'L' |
| **C doesn't confirm** | Not in CONFIRMING state | Press L first, wait for proposal |

**Most Common Issue:** Users press C before locking target or before proposal exists.

**Quick Fix:** Always follow the sequence: **L → Wait → C**

---

## Files to Modify

1. `scripts/run_demo.py` - Add case-insensitive L key, add debug output
2. `src/core/orchestrator.py` - Add debug output for C key handling
3. `configs/default.yaml` - Reduce debounce time
4. `src/input/keyboard_input.py` - Consider case-insensitive C key (optional)



