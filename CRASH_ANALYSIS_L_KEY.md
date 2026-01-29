# Crash Analysis: L Key Press (Forced Lock)

## Executive Summary
The crash occurs due to a **stale state reference** and **race condition** between when `selection_state` is captured and when the forced lock is applied in `orchestrator.step()`.

## Root Cause Analysis

### The Execution Flow (When L is Pressed)

**Frame N (L key pressed):**
```python
# Line 370-373: scripts/run_unified_arm_demo.py
if ord('l') in keys and keys[ord('l')] & p.KEY_WAS_TRIGGERED:
    cube_id = sim.object_id
    if cube_id is not None:
        orchestrator.force_lock_target(cube_id)  # Sets _pending_forced_lock = cube_id
```

**Frame N+1 (Next frame, crash occurs here):**
```python
# Line 257-262: scripts/run_unified_arm_demo.py
if not orchestrator.has_pending_forced_lock():
    selection_state = selector.update(cursor)
else:
    # Skip expensive raycast when forced lock is pending/active
    selection_state = selector.tracker.get_state()  # ⚠️ CAPTURED HERE (BEFORE step)
```

```python
# Line 265: scripts/run_unified_arm_demo.py
snapshot = orchestrator.step(sim, world, selector)  # ⚠️ LOCK APPLIED HERE (AFTER capture)
```

Inside `orchestrator.step()`:
```python
# Line 166-181: src/intent_core/arm_orchestrator.py
world.update_from_sim(sim)  # Updates world state

if self._pending_forced_lock is not None:
    target_id = self._pending_forced_lock
    
    if world.object_state is not None:  # ⚠️ POTENTIAL FAILURE POINT
        world.set_target(target_id, locked=True)
        self.state_machine.set_target(target_id, locked=True)
        selector.force_lock(target_id)  # ⚠️ Updates selector.tracker.state HERE
        self._pending_forced_lock = None
    else:
        print(f"[FORCE LOCK] Waiting for valid object state...")
        # ⚠️ _pending_forced_lock stays set!
```

```python
# Line 269-270: scripts/run_unified_arm_demo.py
if selection_state.locked:  # ⚠️ Uses STALE state from BEFORE step()
    selection_overlay.draw_lock_indicator(selection_state.locked_id)  # ⚠️ CRASH HERE
```

## Critical Issues Identified

### Issue 1: Stale State Reference (PRIMARY CAUSE)
**Location:** `scripts/run_unified_arm_demo.py` lines 257-270

**Problem:**
- `selection_state` is captured at line 262 **BEFORE** `orchestrator.step()` runs
- `orchestrator.step()` applies the forced lock and calls `selector.force_lock()` at line 181
- But `selection_state` still references the **old state** from before the lock was applied
- When rendering tries to access `selection_state.locked_id` at line 270, it may be `None` even though the lock was just applied

**Why it crashes:**
- `selection_state.locked` might be `False` (from before lock)
- But if `selection_state.locked` is somehow `True` but `locked_id` is `None`, accessing `locked_id` could cause issues
- OR: The state object itself might be in an inconsistent state

### Issue 2: Race Condition with Object State
**Location:** `src/intent_core/arm_orchestrator.py` line 173

**Problem:**
- If `world.object_state is None` when forced lock tries to apply:
  - The lock is NOT applied
  - `_pending_forced_lock` stays set (never cleared)
  - Next frame: We skip `selector.update()` again (FIX 6)
  - We get stale `selection_state` again
  - Lock never gets applied, stuck in waiting state

**Why it crashes:**
- If `world.object_state` is `None` initially, the lock never applies
- But `selection_state` might be in an inconsistent state
- Rendering code assumes valid state

### Issue 3: State Object Mutation Timing
**Location:** `src/perception/selection_state.py` and `scripts/run_unified_arm_demo.py`

**Problem:**
- `selector.tracker.get_state()` returns a reference to `self.state` (the actual SelectionState object)
- When `selector.force_lock()` is called, it mutates `self.state` directly
- But `selection_state` was captured BEFORE the mutation
- **However:** Since it's a reference, it SHOULD reflect changes... unless there's a copy happening somewhere

**Why it might crash:**
- If `get_state()` returns a copy instead of reference, changes won't be reflected
- Or if the state object is replaced entirely, the reference becomes stale

## Specific Crash Scenarios

### Scenario A: Object State Not Ready
1. User presses L
2. `force_lock_target()` sets `_pending_forced_lock = cube_id`
3. Next frame:
   - `selection_state = selector.tracker.get_state()` → Gets unlocked state
   - `orchestrator.step()` runs
   - `world.update_from_sim(sim)` → `world.object_state` is still `None` (race condition)
   - Lock NOT applied, `_pending_forced_lock` stays set
   - Rendering uses stale `selection_state` → Potential crash if state is invalid

### Scenario B: Stale Reference After Lock Applied
1. User presses L
2. `force_lock_target()` sets `_pending_forced_lock = cube_id`
3. Next frame:
   - `selection_state = selector.tracker.get_state()` → Gets unlocked state (reference)
   - `orchestrator.step()` runs
   - `world.object_state` is valid
   - `selector.force_lock()` mutates `selector.tracker.state`
   - But `selection_state` reference might not reflect changes immediately
   - Rendering checks `selection_state.locked` → Still `False` (stale)
   - OR: `selection_state.locked` is `True` but `locked_id` is `None` → Crash

### Scenario C: AttributeError on locked_id
1. `selection_state.locked` evaluates to `True` (somehow)
2. Code tries to access `selection_state.locked_id`
3. `locked_id` is `None` or doesn't exist
4. Rendering code crashes when trying to use `None` as object ID

## Code Flow Diagram

```
Frame N (L pressed):
  └─> orchestrator.force_lock_target(cube_id)
      └─> _pending_forced_lock = cube_id

Frame N+1:
  ├─> has_pending_forced_lock() → True
  ├─> selection_state = selector.tracker.get_state()  [CAPTURE POINT]
  │   └─> Returns reference to SelectionState (locked=False, locked_id=None)
  │
  ├─> orchestrator.step()
  │   ├─> world.update_from_sim(sim)
  │   │   └─> world.object_state = read_object_state(sim.object_id)
  │   │       └─> Could return None if object not ready
  │   │
  │   └─> if _pending_forced_lock is not None:
  │       └─> if world.object_state is not None:  [FAILURE POINT]
  │           ├─> world.set_target(target_id, locked=True)
  │           ├─> state_machine.set_target(target_id, locked=True)
  │           ├─> selector.force_lock(target_id)  [MUTATION POINT]
  │           │   └─> tracker.state.locked = True
  │           │   └─> tracker.state.locked_id = target_id
  │           └─> _pending_forced_lock = None
  │       else:
  │           └─> _pending_forced_lock stays set (LOCKED OUT)
  │
  └─> Render selection overlay
      └─> if selection_state.locked:  [USES STALE STATE]
          └─> draw_lock_indicator(selection_state.locked_id)  [CRASH HERE]
```

## Evidence Points

1. **Timing Issue:** `selection_state` captured BEFORE `orchestrator.step()` applies lock
2. **State Validation:** `world.object_state` check can fail, leaving lock pending forever
3. **Reference vs Copy:** Need to verify if `get_state()` returns reference or copy
4. **Null Safety:** Rendering code doesn't check if `locked_id` is `None` before using

## Recommendations (For Future Fix)

1. **Capture selection_state AFTER orchestrator.step():**
   ```python
   snapshot = orchestrator.step(sim, world, selector)
   selection_state = selector.tracker.get_state()  # Get fresh state
   ```

2. **Add null checks in rendering:**
   ```python
   if selection_state.locked and selection_state.locked_id is not None:
       selection_overlay.draw_lock_indicator(selection_state.locked_id)
   ```

3. **Handle object_state None case:**
   - Retry logic for forced lock
   - Or clear `_pending_forced_lock` after timeout
   - Or apply lock even if object_state is None (if object_id is valid)

4. **Verify get_state() behavior:**
   - Ensure it returns reference, not copy
   - Or always get fresh state after step()

## Files Involved

- `scripts/run_unified_arm_demo.py` (lines 257-270) - State capture and rendering
- `src/intent_core/arm_orchestrator.py` (lines 168-184) - Lock application logic
- `src/perception/selection_state.py` (lines 139-141) - State getter method
- `src/perception/target_selector.py` (lines 70-76) - Force lock wrapper



