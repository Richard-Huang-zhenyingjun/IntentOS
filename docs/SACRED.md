# Sacred Files - Do Not Modify

These Phase 2 components are the safety kernel.
Any modification requires full test suite + smoke test verification.

| File | Reason |
|------|--------|
| `src/input/filter.py` | Canonical quality gate and debounce |
| `src/input/router.py` | Canonical routing |
| `src/core/orchestrator.py` `_handle_confirm` | Authorization gate |
| `src/core/authorization.py` | Token issuing |
| `src/execution/primitive_executor.py` | Token-enforced execution |
| `src/core/invariant_checker.py` | `false_executions == 0` |
| `src/execution/hardware_bridge.py` | JOINT protocol bridge |
| `src/robot/hardware/arm_controller.py` | Segmentation + safety clamping |
| `src/input/eeg/device_brainlink.py` | EEG hardware driver |
| `src/input/eeg/device_replay.py` | Replay backend |
| `src/core/system_factory.py` | Only backend switch point |
| `configs/hardware.yaml` `backend: simulator` | Must remain default |

**The invariant `false_executions == 0` is non-negotiable.**
