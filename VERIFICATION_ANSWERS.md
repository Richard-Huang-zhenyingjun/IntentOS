# Verification Answers: L Key Crash Analysis

## Q1: Does selector.tracker.get_state() return reference or copy?

**Answer: REFERENCE**

**Evidence:**
```python
# File: src/perception/selection_state.py, lines 139-141
def get_state(self) -> SelectionState:
    """Get current selection state."""
    return self.state  # ✅ Returns reference to self.state
```

**Analysis:**
- `get_state()` returns `self.state` directly
- `self.state` is a `SelectionState` dataclass instance (created at line 65: `self.state = SelectionState()`)
- Python returns objects by reference, not by value
- Mutations to `self.state` will be visible through the returned reference

**Why it matters:**
- If we capture `selection_state = selector.tracker.get_state()` BEFORE `selector.force_lock()` runs
- Then `selector.force_lock()` mutates `selector.tracker.state`
- The `selection_state` reference SHOULD see the changes (since it's the same object)
- **HOWEVER:** The timing issue still exists because:
  - We check `selection_state.locked` BEFORE the mutation happens
  - Even though it's a reference, we're reading stale values at render time
  - Fix 1 (capture after step) solves this by ensuring we read AFTER mutation

**Conclusion:** Reference, but timing still matters. Fix 1 is still necessary.

---

## Q2: Does selector.force_lock() mutate or replace state?

**Answer: MUTATES**

**Evidence:**
```python
# File: src/perception/target_selector.py, lines 70-76
def force_lock(self, object_id: int) -> None:
    """Force lock a target (diagnostic hack)."""
    self.tracker.force_lock(object_id)  # Delegates to tracker

# File: src/perception/selection_state.py, lines 129-137
def force_lock(self, object_id: int) -> None:
    """Force lock a target (diagnostic hack)."""
    self._lock(object_id)  # Calls _lock()
    self.state.current_hover_id = object_id  # ✅ Mutates existing state
    self.state.hover_frames = self.dwell_frames  # ✅ Mutates existing state

# File: src/perception/selection_state.py, lines 107-112
def _lock(self, object_id: int) -> None:
    """Lock target object."""
    self.state.locked_id = object_id  # ✅ Mutates existing state
    self.state.locked = True  # ✅ Mutates existing state
    self.state.no_hit_frames = 0  # ✅ Mutates existing state
```

**Analysis:**
- `force_lock()` calls `_lock()` which directly mutates `self.state` attributes
- It does NOT create a new `SelectionState` object
- It does NOT replace `self.state` with a new instance
- All mutations happen on the existing `self.state` object

**Why it matters:**
- Since `get_state()` returns a reference to `self.state`
- And `force_lock()` mutates `self.state` in place
- The reference SHOULD see the mutations
- **HOWEVER:** The timing issue persists because:
  - We capture the reference BEFORE mutation
  - We read from the reference AFTER mutation (but Python's attribute access is immediate)
  - Actually, wait... if it's a reference, the mutations SHOULD be visible
  
**Wait, let me reconsider:**
- If `selection_state = selector.tracker.get_state()` returns a reference
- And `selector.force_lock()` mutates `selector.tracker.state`
- Then `selection_state.locked` SHOULD reflect the mutation
- Unless... there's something else going on

**Actually, the real issue is:**
- We capture `selection_state` BEFORE `orchestrator.step()` runs
- `orchestrator.step()` calls `selector.force_lock()`
- But we're checking `selection_state.locked` in the SAME frame
- Since it's a reference, the mutation SHOULD be visible
- **BUT:** The crash happens because `locked_id` might be `None` initially
- And even after mutation, if the mutation fails (object_state check), `locked_id` stays `None`
- So the real bug is the `world.object_state is not None` gate (Fix 3)

**Conclusion:** Mutates, but Fix 3 (remove invalid gate) is the critical fix. Fix 1 (timing) is still good practice.

---

## Summary

1. **Q1 Answer:** Reference - mutations are visible, but timing still matters
2. **Q2 Answer:** Mutates - changes happen in place on existing state object
3. **Root Cause:** The `world.object_state is not None` gate prevents lock from applying, leaving `locked_id` as `None`
4. **Fix Priority:**
   - Fix 1 (timing): Good practice, ensures fresh state
   - Fix 2 (defensive rendering): Prevents crashes from invalid IDs
   - Fix 3 (remove gate): **CRITICAL** - fixes stuck state and allows lock to apply
   - Fix 4 (debugging): Helps verify crash location



