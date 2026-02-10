# Quick Start Guide - Intent Interface Demo

## Running the Demo

### Standard Demo

```bash
python scripts/run_demo.py
```

### Debug Demo (with extensive logging)

```bash
python scripts/run_demo_debug.py
```

### Keyboard Test (isolated keyboard testing)

```bash
python scripts/test_keyboard.py
```

---

## Critical Steps for Keyboard Input

### ⚠️ IMPORTANT: PyBullet GUI Focus Required

**Keyboard input ONLY works when the PyBullet GUI window is focused!**

### Step-by-Step Workflow

1. **Start demo:**
   ```bash
   python scripts/run_demo.py
   ```

2. **IMMEDIATELY click on the PyBullet GUI window**
   - The window must be the active/focused window
   - You should see the 3D simulation (robot arm, cube, plane)

3. **Keep that window focused**
   - Don't click away from the PyBullet window
   - Keep it in the foreground

4. **Try L key to lock target**
   - Press `L` (lowercase or uppercase)
   - Expected: `[ORCH] Forced lock: <cube_id>`
   - State should change: `idle` → `selecting`

5. **Wait for proposal** (1-2 frames)
   - System automatically proposes next action
   - Expected: `[FSM] Proposed: <action> - <reason>`
   - State should change: `selecting` → `confirming`

6. **Press C key to confirm**
   - Press `C` (lowercase or uppercase)
   - Expected: `[KEYBOARD] ✓ CONFIRM pressed`
   - Expected: `[FSM] ✓ Confirmed via keyboard`
   - State should change: `confirming` → `executing`

---

## Controls

| Key | Action | When It Works |
|-----|--------|---------------|
| **L** | Lock target (cube) | Anytime (when GUI focused) |
| **C** | Confirm action | Only when state is `CONFIRMING` (after proposal exists) |
| **X** | Cancel action | Only when state is `CONFIRMING` |
| **R** | Reset system | Anytime (when GUI focused) |
| **Q** | Quit demo | Anytime (when GUI focused) |

---

## Troubleshooting

### L Key Doesn't Work

**Symptoms:**
- Press L but nothing happens
- No console output
- No state change

**Solutions:**
1. ✅ Click on PyBullet GUI window (most common issue)
2. ✅ Check if window is visible (not minimized)
3. ✅ Try uppercase `L` instead of lowercase `l`
4. ✅ Run debug version: `python scripts/run_demo_debug.py`
   - Look for `[KEYS] Detected:` output
   - If no keys detected → GUI not focused

### C Key Doesn't Work

**Symptoms:**
- Press C but nothing happens
- See `[KEYBOARD] ✓ CONFIRM pressed` but no execution

**Solutions:**
1. ✅ Press L first to lock target
2. ✅ Wait for proposal (check state is `CONFIRMING`)
3. ✅ Check console for `[FSM] Proposed:` message
4. ✅ Run debug version to see state transitions:
   ```bash
   python scripts/run_demo_debug.py
   ```

### No Keys Detected At All

**Symptoms:**
- No keyboard input works
- No `[KEYS]` output in debug mode

**Solutions:**
1. ✅ Click on PyBullet GUI window
2. ✅ Make sure window is not minimized
3. ✅ Try running keyboard test: `python scripts/test_keyboard.py`
4. ✅ Check if running in headless mode (remove `--headless` flag)

---

## Expected Console Output

### Successful L Key Press

```
[L KEY] Pressed! Locking cube 2
[L KEY] ✓ Lock command sent
[ORCH] Forced lock: 2
[FSM] Target locked: 2
[STATE] idle → selecting
```

### Successful C Key Press (After Proposal)

```
[KEYBOARD] ✓ CONFIRM pressed
[FSM] ✓ Confirmed via keyboard
[STATE] confirming → executing
```

### Complete Workflow Example

```
[SETUP] Cube ID: 2
[SETUP] Cube valid: True
[L KEY] Pressed! Locking cube 2
[ORCH] Forced lock: 2
[FSM] Target locked: 2
[STATE] idle → selecting
[PROPOSAL] move_up: End effector too low (z=0.15m)
[STATE] selecting → confirming
[KEYBOARD] ✓ CONFIRM pressed
[FSM] ✓ Confirmed via keyboard
[STATE] confirming → executing
```

---

## Environment Setup

### Verify PyBullet Installation

```bash
python scripts/diagnose.py
```

Should show:
- ✓ PyBullet imported successfully
- ✓ All dependencies installed
- ✓ Project structure correct

### Activate Conda Environment (if using)

```bash
conda activate intent_interface
python scripts/run_demo.py
```

---

## Debug Scripts

### 1. Full System Diagnostic
```bash
python scripts/diagnose.py
```
Checks Python environment, dependencies, project structure, imports.

### 2. Keyboard Input Test
```bash
python scripts/test_keyboard.py
```
Isolated keyboard testing - verifies PyBullet keyboard capture works.

### 3. Debug Demo
```bash
python scripts/run_demo_debug.py
```
Full demo with extensive logging - shows state transitions, key detection, proposals.

---

## Common Mistakes

❌ **Pressing C before L**  
✅ Press L first to lock target

❌ **Pressing C before proposal exists**  
✅ Wait for `[FSM] Proposed:` message

❌ **Not focusing PyBullet window**  
✅ Click on window immediately after starting demo

❌ **Running in headless mode**  
✅ Remove `--headless` flag for keyboard input

---

## Quick Reference

**Start demo:** `python scripts/run_demo.py`  
**Focus window:** Click on PyBullet GUI  
**Lock target:** Press `L`  
**Wait for proposal:** ~1-2 frames  
**Confirm:** Press `C`  
**Cancel:** Press `X`  
**Reset:** Press `R`  
**Quit:** Press `Q`

---

## Need More Help?

1. Run diagnostic: `python scripts/diagnose.py`
2. Run keyboard test: `python scripts/test_keyboard.py`
3. Run debug demo: `python scripts/run_demo_debug.py`
4. Check reports:
   - `KEYBOARD_INPUT_ISSUE_REPORT.md` - Detailed keyboard analysis
   - `ENVIRONMENT_ISSUE_REPORT.md` - Environment setup issues


