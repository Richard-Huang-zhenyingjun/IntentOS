# IntentOS Architecture

## Three Layers

### Intent Kernel (Phase 2 - unchanged)

- FSM: IDLE -> AWAITING_CONFIRM -> EXECUTING -> DONE
- Authorization gate: token required per execution
- InvariantChecker: false_executions == 0
- EEG/keyboard -> DecisionPipeline -> DecisionFilter -> Orchestrator

### Orchestration Layer (Phase 3)

- Planner: LLM -> validate -> repair -> heuristic fallback
- World model: heuristic risk estimator
- Checkpoint planner: segment graph by uncertainty + policy
- Proposal engine: human-readable summaries
- Attention budget: rate-limited interruption
- Recovery engine: retry / replan / escalate

### Agent Layer

- AgentBase: execute, can_execute, get_state, emergency_stop
- ArmAgent: wraps Phase 2 PrimitiveExecutor
- SimAgent: simulated second agent for multi-agent testing
- AgentCoordinator: resource conflicts, spatial zones, parallel dispatch

## Data Flow

```text
Goal string
-> AmbiguityResolver (if confidence < 0.7)
-> IntentPlanner.plan()
-> LLM call (or heuristic fallback)
-> TaskGraph validation
-> WorldModel.annotate_graph()
-> ExecutionHistory.annotate_graph()
-> CheckpointPlanner.segment()
-> ProposalEngine.propose()
-> AttentionBudget.can_interrupt()
-> ExecutionKernel.submit_proposal()
-> Phase 2 presents to human
-> Human confirms (EEG or keyboard)
-> ScopedExecutionToken issued
-> AgentCoordinator.execute_segment()
-> AgentBase.execute(action, token) per node
-> ExecutionHistory.record()
-> SystemMemory.record_object_action()
-> RecoveryEngine (on failure)
-> InvariantChecker.assert_invariant()
```

## Uncertainty Model

Three signals, weighted combination:

- `perception_confidence` (0.35 weight) - vision YOLO score
- `execution_history_rate` (0.35 weight) - from ExecutionHistory
- `simulation_risk` (0.30 weight) - from WorldModel

Thresholds:

- combined < 0.2 -> execute silently
- 0.2-0.5 -> note in proposal, no interrupt
- 0.5-0.7 -> checkpoint boundary
- 0.7-0.85 -> always confirm
- > 0.85 -> abort plan

## Sacred Files (Never Modify)

See SACRED.md for the complete list.
