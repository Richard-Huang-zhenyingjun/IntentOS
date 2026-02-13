# Debug Demo Workflow Guide

## Running the Debug Demo

```bash
python scripts/run_demo_debug.py
```

**Note:** Cannot run in Cursor's sandbox due to GUI restrictions. Run in Terminal.app instead.

---

## Complete Workflow

### Step 1: Start Demo
```bash
python scripts/run_demo_debug.py
```

**Expected output:**
```
======================================================================
INTENT INTERFACE DEMO - DEBUG MODE
======================================================================

Philosophy: SELECT → PROPOSE → CONFIRM → EXECUTE
Safety: false_executions == 0

[SIM] Connected to PyBullet GUI
[SIM] PyBullet data path: /path/to/pybullet_data
[SIM] Loading plane...
[SIM] ✓ Plane loaded (id=0)
[SIM] Loading KUKA IIWA arm...
[SIM] ✓ Robot loaded (id=1)
[SIM] Loading cube...
[SIM] ✓ Cube loaded (id=2)

[SETUP] Cube ID: 2
[SETUP] Cube valid: True
Input: Keyboard (C=confirm, X=cancel)

[ORCH] ✓ Orchestrator initialized
[ORCH]   Input: Keyboard (C=confirm, X=cancel)

Controls:
  L - Lock target (cube)
  C - Confirm action (only works when proposal exists!)
  X - Cancel action
  R - Reset system
  Q - Quit

======================================================================
IMPORTANT: Click on PyBullet window to focus it!
======================================================================

Running...
```

---

### Step 2: Click PyBullet Window ⚠️ CRITICAL

**Action:** Click on the PyBullet GUI window to focus it

**Why:** Keyboard input only works when the window is focused

**Visual:** You should see the 3D simulation (robot arm, cube, plane)

---

### Step 3: Press L Key

**Action:** Press `L` (lowercase or uppercase)

**Expected output:**
```
[L KEY] Pressed! Locking cube 2
[L KEY] ✓ Lock command sent
[ORCH] Forced lock: 2
[FSM] Target locked: 2
[STATE] None → idle
[STATE] idle → selecting
```

**What happened:**
- ✅ L key detected
- ✅ Cube locked
- ✅ State changed: `idle` → `selecting`

**If you don't see this:**
- ❌ PyBullet window not focused → Click on it
- ❌ No `[L KEY]` message → Window not focused
- ❌ No state change → Check console for errors

---

### Step 4: Wait for Proposal

**Action:** Wait 1-2 frames (~0.03 seconds)

**Expected output:**
```
[PROPOSAL] move_up: End effector too low (z=0.15m)
[FSM] Proposed: move_up - End effector too low (z=0.15m)
[STATE] selecting → confirming
```

**What happened:**
- ✅ Planner proposed next action (`move_up`, `reach`, `grasp`, or `place`)
- ✅ State changed: `selecting` → `confirming`
- ✅ System is now waiting for confirmation

**Alternative proposals you might see:**
- `[PROPOSAL] reach: Moving to object (distance=0.20m)`
- `[PROPOSAL] grasp: Close enough to grasp`
- `[PROPOSAL] place: Holding object 2, ready to place`

---

### Step 5: Press C Key

**Action:** Press `C` (lowercase or uppercase)

**Expected output:**
```
[KEYBOARD] ✓ CONFIRM pressed
[FSM] ✓ Confirmed via keyboard
[ORCH] C key detected in CONFIRMING state
[STATE] confirming → executing
```

**What happened:**
- ✅ C key detected
- ✅ Confirmation processed
- ✅ State changed: `confirming` → `executing`
- ✅ Action execution started

**If you don't see this:**
- ❌ No `[KEYBOARD] ✓ CONFIRM pressed` → Window not focused
- ❌ No state change → Check if proposal exists (should see `[PROPOSAL]` first)
- ❌ State is `selecting` not `confirming` → Wait longer for proposal

---

### Step 6: Action Executes

**Expected output:**
```
[CTRL] → Moving to [0.5 0.0 0.3]
[CTRL] ✓ Motion complete (error=0.0045)
[FSM] ✓ Execution complete
[STATE] executing → done
```

**What happened:**
- ✅ Action executed successfully
- ✅ State changed: `executing` → `done`
- ✅ Ready for next action

---

## Complete Example Output

```
[SETUP] Cube ID: 2
[SETUP] Cube valid: True

[L KEY] Pressed! Locking cube 2
[L KEY] ✓ Lock command sent
[ORCH] Forced lock: 2
[FSM] Target locked: 2
[STATE] None → idle
[STATE] idle → selecting

[PROPOSAL] move_up: End effector too low (z=0.15m)
[FSM] Proposed: move_up - End effector too low (z=0.15m)
[STATE] selecting → confirming

[KEYBOARD] ✓ CONFIRM pressed
[FSM] ✓ Confirmed via keyboard
[ORCH] C key detected in CONFIRMING state
[STATE] confirming → executing

[CTRL] → Moving to [0.5 0.0 0.3]
[CTRL] ✓ Motion complete (error=0.0045)
[FSM] ✓ Execution complete
[STATE] executing → done
```

---

## Troubleshooting

### L Key Doesn't Work

**Symptoms:**
- Press L but nothing happens
- No `[L KEY]` output

**Solutions:**
1. ✅ Click on PyBullet window (most common)
2. ✅ Check window is visible (not minimized)
3. ✅ Try uppercase `L` instead of lowercase
4. ✅ Look for `[KEYS] Detected:` output (if none, window not focused)

### C Key Doesn't Work

**Symptoms:**
- Press C but nothing happens
- See `[KEYBOARD] ✓ CONFIRM pressed` but no execution

**Solutions:**
1. ✅ Press L first to lock target
2. ✅ Wait for `[PROPOSAL]` message
3. ✅ Check state is `confirming` (not `selecting`)
4. ✅ Look for `[STATE] selecting → confirming` transition

### No Keys Detected

**Symptoms:**
- No `[KEYS] Detected:` output
- No keyboard input works

**Solutions:**
1. ✅ Click on PyBullet window
2. ✅ Make sure window is not minimized
3. ✅ Try running keyboard test: `python scripts/test_keyboard.py`

---

## Debug Output Reference

| Output | Meaning |
|--------|---------|
| `[SETUP] Cube ID: X` | Cube loaded successfully |
| `[L KEY] Pressed!` | L key detected |
| `[STATE] A → B` | State machine transition |
| `[PROPOSAL] action: reason` | Action proposed, ready for confirmation |
| `[KEYBOARD] ✓ CONFIRM pressed` | C key detected |
| `[KEYS] Detected: L, C` | Keyboard events captured |
| `[FRAME N]` | Periodic state summary |

---

## Quick Checklist

- [ ] Demo started
- [ ] PyBullet window visible
- [ ] Clicked on window to focus
- [ ] Pressed L → Saw `[L KEY] Pressed!`
- [ ] Saw state change: `idle → selecting`
- [ ] Saw `[PROPOSAL]` message
- [ ] Saw state change: `selecting → confirming`
- [ ] Pressed C → Saw `[KEYBOARD] ✓ CONFIRM pressed`
- [ ] Saw state change: `confirming → executing`
- [ ] Action executed successfully

---

## Next Steps

After confirming the workflow works:

1. **Run standard demo:** `python scripts/run_demo.py`
2. **Test all keys:** L, C, X, R, Q
3. **Try full sequence:** L → Wait → C → Wait → L → Wait → C (repeat)

---

## Files

- **Debug demo:** `scripts/run_demo_debug.py`
- **Standard demo:** `scripts/run_demo.py`
- **Keyboard test:** `scripts/test_keyboard.py`
- **Diagnostic:** `scripts/diagnose.py`



