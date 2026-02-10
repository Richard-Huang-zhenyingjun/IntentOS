# Test Coverage Baseline

Generated: 2026-02-10

## Overall Coverage
- Total: 68%
- `src/core/`: 73.50%
- `src/execution/`: 85.45%
- `src/planning/`: 39.31%
- `src/intelligence/`: 71.43%

## Critical Modules (>80% required)
- `src/core/orchestrator.py`: 63.16%
- `src/core/authorization.py`: 95.29%
- `src/core/trust.py`: 89.47%
- `src/execution/primitive_executor.py`: 88.24%

## Known Gaps
- `src/core/orchestrator.py`: lines `221`, `250`, `254`, `256`, `271`, `285-286` (plus additional branches)
  - Reason: many runtime-only branches (pause/re-auth/error/control-loop variants) remain hard to deterministically reach.
  - Acceptable: no
  - Plan: add focused branch tests around cancel flow, pause/resume branches, and remaining execution error handlers.
- `src/core/diag.py`: lines `21-22`, `25-26`, `40-46`, `51-52`, `59`, `91-92` (plus additional branches)
  - Reason: diagnostics path matrix (missing env/config/runtime resources) not fully enumerated.
  - Acceptable: yes (non-control logic)
  - Plan: add table-driven tests for each diagnostic failure/warning condition.
- `src/planning/planner.py`: broad uncovered surface (currently 0%)
  - Reason: legacy planner path not exercised by current orchestrator integration tests.
  - Acceptable: no (batch target not met)
  - Plan: add direct unit tests for action priority selection and rationale generation.
- `src/planning/preconditions.py`: broad uncovered surface (currently 0%)
  - Reason: precondition engine currently bypassed in the newer plan-compiler-oriented flow.
  - Acceptable: no (batch target not met)
  - Plan: add direct unit tests for move-up/reach/grasp/place predicates and edge thresholds.
- `src/execution/safe_pause.py`: lines `58`, `61`, `66`, `73`, `78`, `85`
  - Reason: grasping branch and metadata-specific branches partially covered only.
  - Acceptable: yes (module already above 70 and execution package above target)
  - Plan: add one extra test covering grasping=True full sequence with metadata checks.

## Coverage Gate
- All PRs should maintain or improve coverage.
- No `src/core/*` or `src/execution/*` critical module should regress once above 80%.
- Current status:
  - `src/execution/*` package target met (>80%).
  - `src/intelligence/*` package target met (>60%).
  - `src/core/*` package target not met (73.50% < 80%).
  - `src/planning/*` package target not met (39.31% < 70%).
