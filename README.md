# IntentOS - Intent-Orchestrated Multi-Agent System

An orchestration layer that lets one human control robotic agents through
high-level intent with minimal attention.

**Core claim:** A human's neural intent signal can gate robotic task execution
with zero false executions.

## Architecture

```text
Human goal
-> Planner (LLM + validation + heuristic fallback)
-> World model (heuristic risk estimation)
-> Checkpoint authorization (scoped execution tokens)
-> AgentCoordinator (parallel dispatch, resource safety)
-> Phase 2 kernel (false_executions == 0)
-> Physical arm
```

## Quick Start

```bash
# Simulation only (no hardware)
python scripts/run_intentos_demo.py --goal "clean the table" --no-llm

# With LLM planning (requires GEMINI_API_KEY)
python scripts/run_intentos_demo.py --goal "clean the table"

# Real arm (requires hardware setup - see docs/hardware_setup.md)
python scripts/run_intentos_demo.py --config configs/real_arm.yaml
```

## Safety Invariant

`false_executions == 0` is verified every tick. No action executes without
an explicit human confirmation and a valid scoped execution token.

## Phase Structure

| Phase | What | Status |
|-------|------|--------|
| Phase 2 | EEG authorization + arm execution | Complete |
| 3A | Kernel boundary + agent interface | Complete |
| 3B | Planner + proposal engine | Complete |
| 3C | World model + scoped tokens + recovery | Complete |
| 3D | Multi-agent coordination | Complete |
| 3E | Ambiguity, memory, docs, demo | This phase |

## Running Tests

```bash
# Full suite (must be >= 398 passed)
pytest tests/ -v --tb=short

# IntentOS tests only
pytest tests/test_execution_kernel.py tests/test_agent_base.py \
       tests/test_task_graph.py tests/test_planner.py \
       tests/test_world_model.py tests/test_agent_coordinator.py -v

# Invariant verification
pytest tests/ -v -k "invariant"
```

## Key Design Decisions

1. **Phase 2 is untouched.** IntentOS wraps it, never modifies it.
2. **LLM calls are isolated to `src/planning/planner.py`.** No LLM in execution loop.
3. **EEG is confirm/cancel only.** Never used for option selection.
4. **Heuristic fallback always works.** System degrades gracefully when LLM fails.
5. **Scoped tokens reduce confirmations.** One confirm per checkpoint segment, not per primitive.
