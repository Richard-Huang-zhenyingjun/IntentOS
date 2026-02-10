# Frozen Interfaces

This document captures the current interface contracts from source and defines what is stable vs internal.

## 1) `Orchestrator.step()` -> return type

Source: `src/core/orchestrator.py:154`

Actual signature:
```python
def step(self) -> UISnapshot:
```

Observed behavior contract:
- Advances one control-frame of the system (simulation, sensing, decision pipeline, FSM, execution).
- Returns a `UISnapshot` every call (`src/core/orchestrator.py:248`).

Must not change:
- Method name `step`.
- Call shape: no required args.
- Return type contract: returns `UISnapshot`.
- One-call = one frame progression semantics.

Can change internally:
- Internal ordering/details of sensing/planning/execution phases.
- Logging/diagnostic messages.
- Additional internal safety checks/assertions.

## 2) Controller motion API (`move_to_position`, `update`, `is_executing`)

Source: `src/robot/controller.py`

Actual signatures:
```python
def move_to_position(self, target_xyz: np.ndarray):
def update(self, current_state: ArmState) -> bool:
def is_executing(self) -> bool:
```

Multi-frame semantics (actual):
- `move_to_position(...)` starts a motion target and returns immediately (`src/robot/controller.py:44`).
- `update(...)` must be called each frame to apply motor commands and check convergence (`src/robot/controller.py:67`).
- `update(...)` returns `True` only when settled for configured frames; otherwise `False`.
- `is_executing()` reports motion-in-progress state (`src/robot/controller.py:162`).

Must not change:
- Non-blocking start semantics of `move_to_position(...)`.
- `update(...)` boolean meaning: `True` = completed/settled this motion.
- `is_executing()` boolean meaning.

Can change internally:
- IK solver details, gains, convergence thresholds, settle logic implementation.
- Diagnostic output and telemetry fields.

## 3) Frozen dataclasses in `src/interfaces/`

Frozen (`@dataclass(frozen=True)`):
- `Decision` (`src/interfaces/decision_source_base.py:9`)
- `IntentProposal` (`src/interfaces/intent_proposal.py:19`)
- `ObjectInfo` (`src/interfaces/scene_summary.py:11`)
- `SceneSummary` (`src/interfaces/scene_summary.py:22`)

Not frozen (`@dataclass` only) - potential mutability risk:
- `Primitive` (`src/interfaces/primitive.py:13`)
- `WorldArtifacts` (`src/interfaces/world_artifacts.py:4`)

Must not change:
- Frozen status of the four frozen contracts above (unless a coordinated breaking-change migration is done).
- Field meanings used by orchestrator/planner/proposer boundaries.

Can change internally:
- Non-interface module-local dataclass usage.
- Additive fields with safe defaults (requires compatibility review).

## 4) `EventEmitter.emit()` and JSONL contract

Source: `src/core/events.py:65`

Actual signature:
```python
def emit(
    self,
    event_type: EventType,
    frame: Optional[int] = None,
    data: Optional[Dict[str, Any]] = None
):
```

Observed emitter behavior:
- If disabled, no-op.
- Ensures `data` is a dict.
- Injects `data['frame'] = frame` when frame is provided.
- Logs and invokes registered handlers with `(event_type, data)`.

JSONL format contract (consumed by tools/tests):
- Replay/export tools expect each JSONL line shaped like:
  - `{"event_type": str, "frame": int, "data": dict}`
- See consumers: `src/tools/replay_events.py`, `src/tools/export_trust_csv.py`, tests in `tests/test_replay_parser.py`.
- Note: `EventEmitter` itself does not currently write JSONL; this shape is a handler/output contract.

Must not change:
- `emit(...)` call signature above.
- Handler callback contract `(event_type, data)`.
- External JSONL key names expected by tools: `event_type`, `frame`, `data`.

Can change internally:
- Logging backend and handler storage implementation.
- Additional metadata in `data` payloads.

## 5) `DecisionPipeline.tick()` -> return type

Source: `src/input/pipeline.py:34`

Actual signature:
```python
def tick(self, frame_number: int) -> DecisionFrame:
```

Observed behavior contract:
- Executes one pipeline frame: source routing -> decision filtering -> optional event emission.
- Returns a `DecisionFrame` every call.

Must not change:
- Method name `tick`.
- Required argument `frame_number: int`.
- Return type contract `DecisionFrame`.

Can change internally:
- Routing/filter strategy details.
- Event emission conditions and extra metadata fields.
