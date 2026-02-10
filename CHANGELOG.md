# Changelog

## Week 8 — End-to-End Demo Hardening (Feb 2026)
### Added
- Production-grade demo script with startup diagnostics, graceful shutdown, and metrics export.
- Comprehensive overlay enhancements with trust/status visibility and clearer runtime messaging.
- Session metrics collection (`src/core/metrics.py`) and JSON export support.
- Graceful error recovery coverage for EEG/device/input/runtime failure modes.
- Multi-seed stress testing, long-run stability tests, and fault-injection tests.
- Expanded false-executions invariant verification and authorization safety checks.
- Demo artifact bundle and replay documentation under `demo_artifacts/`.

### Changed
- Overlay layout and status rendering were restructured for readability and operational transparency.
- Startup diagnostics now provide structured summaries and clearer fail-fast behavior.
- User-facing runtime error messages and shutdown paths are now explicit and non-crashing.

### Fixed
- `tests/test_core_safety.py::test_false_executions_zero`: updated test wiring to match current `Orchestrator` constructor shape.
- `tests/test_clean_table_integration.py` failures: fixed test setup/wiring mismatches against current composition path.
- Baseline failing test batch resolved to stable green test runs before Week 8 hardening tasks.

## Week 7 — Safety-First Shared Autonomy (Jan 2026)
### Added
- Token-based authorization gating and re-auth flows.
- Trust engine with deterministic penalties/recovery and re-auth triggers.
- Autonomy policy support (A1/A2) and safe-pause flow.
- Event-based observability for auth/trust/autonomy transitions.

### Changed
- Orchestrator flow updated to enforce authorization before execution.
- Decision and execution pipeline integration tightened around safety-first state transitions.

### Fixed
- Keyboard-to-pipeline wiring issues that could bypass intended confirmation path.
- Safe-pause/re-auth sequencing regressions around token lifecycle handling.
