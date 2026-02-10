# Architecture — Intent-Authorized Robotic Manipulation System

## Philosophy

`SELECT → PROPOSE → CONFIRM → EXECUTE`

The system keeps intent selection and action execution explicitly separated, with authorization checks at execution time.

## Tier Structure

1. `src/interfaces/` (contracts only)
- Frozen dataclasses, interface protocols, and abstract contracts.
- Must not import concrete runtime modules.

2. Core orchestration layer (`src/core/`, `src/execution/`)
- Orchestrator, authorization, trust logic, execution flow, state machine.
- Depends on interfaces and injected collaborators, not provider-specific concrete implementations.

3. Adapter/integration layer (`src/input/`, `src/intelligence/`, `src/robot/`, `src/worlds/`, `src/external/`)
- Concrete IO, planners/proposers, simulator/world adapters, external services (Gemini/EEG).
- Wired together by `src/core/system_factory.py`.

## Safety Invariants

1. `false_executions == 0`
2. No network calls during `EXECUTING`
3. Tier-1 style boundary: core logic relies on interface contracts and injected dependencies, not direct external provider imports

## Data Flow

1. Input sources (`KeyboardSource`, EEG source, or test source) produce raw decision signals.
2. `DecisionRouter` merges source signals per policy.
3. `DecisionFilter` enforces debounce/quality/hold rules.
4. `DecisionPipeline.tick()` returns a `DecisionFrame` to `Orchestrator.step()`.
5. Orchestrator updates state machine (`IDLE/SELECTING/CONFIRMING/EXECUTING/...`).
6. On confirm, authorization token is issued and plan compilation starts.
7. `PrimitiveExecutor.tick()` advances primitive execution.
8. Trust/authorization/event streams are updated and emitted through `EventEmitter`.
9. UI snapshot is produced for overlay and diagnostics.

## Testing Strategy

- Unit tests:
  - Router/filter invariants (`tests/test_decision_router.py`, `tests/test_decision_filter.py`)
  - Auth/trust/token guarantees (`tests/test_authorization_token.py`, `tests/test_trust_engine.py`)
- Integration tests:
  - Clean-table orchestration and confirm-gate behavior (`tests/test_clean_table_integration.py`)
  - System assembly/wiring (`tests/test_system_factory.py`)
- Safety tests:
  - False execution invariant and execution gate checks (`tests/test_core_safety.py`, `tests/test_false_executions_invariant.py`)
- Robustness/stress tests:
  - Repeatability and long-running stability (`tests/test_repeatability_seeds.py`, `tests/test_long_running_stability.py`)
  - Fault injection recovery behavior (`tests/test_fault_injection.py`)
