# Q Key vs L Key Debug Output Comparison

## Expected Outputs Side-by-Side

### When Pressing Q Key (Should Work)

```
[DEBUG FRAME] Keys detected: ['q']
[DEBUG FRAME] L key code 108 in keys: False
[DEBUG Q] Checking Q key condition...
  ord('q') in keys = True
  keys[ord('q')] = 2
  keys[ord('q')] & p.KEY_WAS_TRIGGERED = 2
[DEBUG Q] >>> QUITTING
[DEMO] Quitting...
```

### When Pressing L Key (Currently Not Working)

**If L key is detected:**
```
[DEBUG FRAME] Keys detected: ['l']
[DEBUG FRAME] L key code 108 in keys: True
[DEBUG FRAME] L key state: 2, TRIGGERED: True
[DEBUG L] Checking L key condition...
  ord('l') = 108
  ord('l') in keys = True
  keys[ord('l')] = 2
  p.KEY_WAS_TRIGGERED = 2
  keys[ord('l')] & p.KEY_WAS_TRIGGERED = 2
[DEBUG L] l_pressed = True
[DEBUG L] >>> INSIDE L KEY HANDLER!
[DEBUG L] About to check cube_id:
  sim.cube_id = 2
  sim.cube_id is not None = True
[DEBUG L] >>> Calling force_lock_target(2)
[DEMO] Locking target: 2
[ORCH] Forced lock: 2
```

**If L key is NOT detected:**
```
[DEBUG FRAME] Keys detected: []  ← Empty!
[DEBUG FRAME] L key code 108 in keys: False
[DEBUG L] Checking L key condition...
  ord('l') = 108
  ord('l') in keys = False
[DEBUG L] l_pressed = False
```

---

## What to Compare

### 1. Key Detection
- **Q key:** `[DEBUG FRAME] Keys detected: ['q']` ✓
- **L key:** `[DEBUG FRAME] Keys detected: ['l']` or `[]` ?

### 2. Key in Dictionary Check
- **Q key:** `ord('q') in keys = True` ✓
- **L key:** `ord('l') in keys = True` or `False` ?

### 3. Key State Value
- **Q key:** `keys[ord('q')] = 2` ✓
- **L key:** `keys[ord('l')] = 2` or different?

### 4. TRIGGERED Flag
- **Q key:** `keys[ord('q')] & p.KEY_WAS_TRIGGERED = 2` ✓
- **L key:** `keys[ord('l')] & p.KEY_WAS_TRIGGERED = 2` or `0`?

### 5. Handler Execution
- **Q key:** `[DEBUG Q] >>> QUITTING` ✓
- **L key:** `[DEBUG L] >>> INSIDE L KEY HANDLER!` or not reached?

---

## Diagnostic Scenarios

### Scenario 1: L Key Not Detected at All
**Output:**
```
[DEBUG FRAME] Keys detected: []  ← No keys!
[DEBUG L] ord('l') in keys = False
```
**Problem:** PyBullet window not focused, or keyboard input not working

### Scenario 2: L Key Detected But Wrong State
**Output:**
```
[DEBUG FRAME] Keys detected: ['l']
[DEBUG L] ord('l') in keys = True
[DEBUG L] keys[ord('l')] = 1  ← Not 2!
[DEBUG L] keys[ord('l')] & p.KEY_WAS_TRIGGERED = 0  ← Not triggered!
```
**Problem:** Key state flag issue - key detected but not in TRIGGERED state

### Scenario 3: L Key Detected Correctly But Handler Not Reached
**Output:**
```
[DEBUG FRAME] Keys detected: ['l']
[DEBUG L] ord('l') in keys = True
[DEBUG L] keys[ord('l')] = 2
[DEBUG L] keys[ord('l')] & p.KEY_WAS_TRIGGERED = 2
[DEBUG L] l_pressed = True
(But no "[DEBUG L] >>> INSIDE L KEY HANDLER!")
```
**Problem:** Logic error in condition evaluation

### Scenario 4: Handler Reached But cube_id Issue
**Output:**
```
[DEBUG L] >>> INSIDE L KEY HANDLER!
[DEBUG L] sim.cube_id = None  ← Problem!
[DEBUG L] >>> cube_id is None!
```
**Problem:** cube_id not set or lost

---

## Testing Steps

1. **Run demo:** `python scripts/run_demo.py`
2. **Click PyBullet window** to focus it
3. **Press Q once:**
   - Copy all `[DEBUG Q]` output
   - Demo should quit
4. **Restart demo:** `python scripts/run_demo.py`
5. **Click PyBullet window** again
6. **Press L once:**
   - Copy all `[DEBUG FRAME]` and `[DEBUG L]` output
7. **Compare outputs** using the scenarios above

---

## Key Questions

1. **Are both keys detected?**
   - Q: `Keys detected: ['q']`?
   - L: `Keys detected: ['l']`?

2. **Do both have same key state?**
   - Both should show `keys[ord('X')] = 2`
   - Both should show `& p.KEY_WAS_TRIGGERED = 2`

3. **Do both reach their handlers?**
   - Q: `[DEBUG Q] >>> QUITTING`?
   - L: `[DEBUG L] >>> INSIDE L KEY HANDLER!`?

4. **If L handler reached, is cube_id valid?**
   - Should show `sim.cube_id = 2` (or valid int)
   - Should show `sim.cube_id is not None = True`

---

## Expected Working Output (Both Keys)

Both should look identical except for the key character:

**Q Key:**
```
[DEBUG FRAME] Keys detected: ['q']
[DEBUG Q] Checking Q key condition...
  ord('q') in keys = True
  keys[ord('q')] = 2
  keys[ord('q')] & p.KEY_WAS_TRIGGERED = 2
[DEBUG Q] >>> QUITTING
```

**L Key:**
```
[DEBUG FRAME] Keys detected: ['l']
[DEBUG L] Checking L key condition...
  ord('l') = 108
  ord('l') in keys = True
  keys[ord('l')] = 2
  p.KEY_WAS_TRIGGERED = 2
  keys[ord('l')] & p.KEY_WAS_TRIGGERED = 2
[DEBUG L] l_pressed = True
[DEBUG L] >>> INSIDE L KEY HANDLER!
[DEBUG L] About to check cube_id:
  sim.cube_id = 2
  sim.cube_id is not None = True
[DEBUG L] >>> Calling force_lock_target(2)
```

If they differ, that's where the problem is!


