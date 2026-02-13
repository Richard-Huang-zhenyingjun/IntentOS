# Why L Key Doesn't Work - Root Cause Analysis

## The Problem

**Symptom:** Pressing L key produces no response in the simulation.

**Root Cause:** Keyboard buffer is being cleared before the demo script can read the L key.

---

## Code Flow Analysis

### Current Execution Order (Per Frame)

```
Frame N:
1. orch.step() is called
   └─> KeyboardInput.read_decision() is called
       └─> p.getKeyboardEvents() ← READS ALL KEYS (including L!)
           └─> Checks for C/X only
           └─> BUFFER CLEARED (even though L was read but ignored)
           
2. Demo script calls p.getKeyboardEvents()
   └─> BUFFER IS EMPTY! ← L key is gone!
   └─> No L key detected
```

### The Critical Issue

**`p.getKeyboardEvents()` clears the keyboard buffer after reading.**

When `KeyboardInput.read_decision()` calls `p.getKeyboardEvents()`, it:
- ✅ Reads ALL keys (including L, R, Q, etc.)
- ✅ Only processes C and X
- ❌ **Clears the buffer** (even for keys it doesn't care about!)
- ❌ Demo script gets empty buffer

---

## Visual Example

```
User presses L key
    ↓
Frame starts
    ↓
orch.step() called
    ↓
KeyboardInput.read_decision()
    ↓
p.getKeyboardEvents() → {108: 2}  ← L key code 108
    ↓
Checks: Is 108 == ord('c')? NO
Checks: Is 108 == ord('x')? NO
    ↓
Ignores L key
    ↓
Returns ArmDecision(signal=IDLE)
    ↓
BUFFER CLEARED ← L key lost!
    ↓
Demo script: p.getKeyboardEvents() → {}  ← Empty!
    ↓
L key handler never executes
```

---

## Why This Happens

### PyBullet's `getKeyboardEvents()` Behavior

```python
keys = p.getKeyboardEvents()
# Returns: {key_code: key_state, ...}
# Side effect: CLEARS the keyboard buffer
```

**Key Point:** Each call to `getKeyboardEvents()` consumes ALL pending keyboard events, not just the ones you check.

### Current Architecture

```
KeyboardInput.read_decision()
├─ Reads ALL keys
├─ Processes C/X only
└─ Clears buffer (loses L, R, Q)

Demo script
├─ Reads buffer (empty!)
└─ Can't detect L, R, Q
```

---

## Solutions

### Solution 1: Share Keyboard Events (RECOMMENDED)

**Modify `KeyboardInput.read_decision()` to accept pre-read keys:**

```python
# In orchestrator.step():
keys = p.getKeyboardEvents()  # Read ONCE per frame
decision = self.decision_source.read_decision(keys)  # Pass keys
```

**Modify `KeyboardInput.read_decision()`:**

```python
def read_decision(self, keys: dict = None) -> ArmDecision:
    if keys is None:
        keys = p.getKeyboardEvents()  # Fallback
    
    # Process C/X only
    # Don't clear buffer - return keys for demo script
```

**Problem:** Requires architecture change.

---

### Solution 2: Read Keys Once, Distribute (BEST)

**Read keys once in demo script, pass to both:**

```python
# In run_demo.py main loop:
keys = p.getKeyboardEvents()  # Read ONCE

# Pass to orchestrator
decision = orch.step_with_keys(keys)

# Use for demo controls
if ord('l') in keys:
    # Handle L
```

**Problem:** Requires refactoring orchestrator interface.

---

### Solution 3: Filter Keys Before Clearing (SIMPLE FIX)

**Modify `KeyboardInput.read_decision()` to only read C/X:**

```python
def read_decision(self) -> ArmDecision:
    # Read all keys
    all_keys = p.getKeyboardEvents()
    
    # Extract only C/X
    relevant_keys = {}
    if self.CONFIRM_KEY in all_keys:
        relevant_keys[self.CONFIRM_KEY] = all_keys[self.CONFIRM_KEY]
    if self.CANCEL_KEY in all_keys:
        relevant_keys[self.CANCEL_KEY] = all_keys[self.CANCEL_KEY]
    
    # Process C/X
    # ...
    
    # CRITICAL: Don't clear buffer - return unused keys
    # But PyBullet already cleared it! 😞
```

**Problem:** PyBullet clears buffer automatically - can't prevent it.

---

### Solution 4: Read Keys Twice (WORKAROUND)

**Read keys BEFORE orchestrator.step():**

```python
# In run_demo.py:
keys = p.getKeyboardEvents()  # Read L/R/Q FIRST

# Store L/R/Q state
l_pressed = (ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED)

# Then call orchestrator (reads C/X)
snapshot = orch.step()

# Use stored L/R/Q state
if l_pressed:
    orch.force_lock_target(sim.cube_id)
```

**Problem:** C/X keys might be lost if pressed with L.

---

### Solution 5: Merge Both Reads (RECOMMENDED FIX)

**Read keys once, check both C/X and L/R/Q:**

```python
# In run_demo.py main loop:
keys = p.getKeyboardEvents()  # Read ONCE

# Check C/X for orchestrator
c_pressed = (ord('c') in keys and keys[ord('c')] & p.KEY_WAS_TRIGGERED)
x_pressed = (ord('x') in keys and keys[ord('x')] & p.KEY_WAS_TRIGGERED)

# Create decision manually
if c_pressed:
    decision = ArmDecision(signal=DecisionSignal.CONFIRM, ...)
elif x_pressed:
    decision = ArmDecision(signal=DecisionSignal.CANCEL, ...)
else:
    decision = ArmDecision(signal=DecisionSignal.IDLE, ...)

# Pass to orchestrator
snapshot = orch.step_with_decision(decision)

# Check L/R/Q
if ord('l') in keys:
    # Handle L
```

**Problem:** Bypasses KeyboardInput abstraction.

---

## Recommended Fix: Solution 5 (Simplest)

**Modify the main loop to read keys once and distribute:**

1. Read `p.getKeyboardEvents()` ONCE per frame
2. Check C/X and create `ArmDecision` manually
3. Pass decision to orchestrator (or modify orchestrator to accept decision)
4. Check L/R/Q from same keys dict

This ensures:
- ✅ All keys are captured
- ✅ No buffer clearing issues
- ✅ C/X still work for orchestrator
- ✅ L/R/Q work for demo script

---

## Quick Test

Add this debug code to verify the issue:

```python
# In run_demo.py, before orch.step():
keys_before = p.getKeyboardEvents()
print(f"[DEBUG] Keys before orchestrator: {keys_before}")

snapshot = orch.step()

keys_after = p.getKeyboardEvents()
print(f"[DEBUG] Keys after orchestrator: {keys_after}")
```

**Expected output when pressing L:**
```
[DEBUG] Keys before orchestrator: {}  ← Empty (orchestrator already read)
[DEBUG] Keys after orchestrator: {}   ← Still empty
```

**If you see L key in `keys_before` but not `keys_after`, that confirms the issue.**

---

## Summary

**Root Cause:** `KeyboardInput.read_decision()` calls `p.getKeyboardEvents()` which clears the buffer, consuming the L key before the demo script can read it.

**Fix:** Read keyboard events ONCE per frame and distribute to both orchestrator and demo script.



