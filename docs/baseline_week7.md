# Week 7 Baseline Lock

## Run Command
`python scripts/run_demo.py`

## Keyboard
- `L` = lock target
- `C` = confirm
- `X` = cancel
- `R` = reset
- `Q` = quit

## Known Issues
1. `last_affordance_result` -> `current_affordances` mismatch.
2. `RecoveryController.check()` missing (current method is `check_and_plan()`).
3. `ActionRecord` API mismatch in tests.
4. `HandDetectionResult` missing `hand_position` in tests.
5. `SmartWorldSim.apply_action()` API mismatch in tests.

## Test Count
- `123 passed`
- `0 failed`
- `4 skipped`
