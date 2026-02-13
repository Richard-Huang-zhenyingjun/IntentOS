# OpenVLA Integration Guide

## Overview

The Intent-Authorized Robotic Manipulation System integrates OpenVLA
(a pre-trained vision-language-action model) as a manipulation proposer,
wrapped in a safety layer that requires explicit user authorization
before any execution.

## Architecture

User Input (EEG/Keyboard) -> SELECT object  
↓  
ProposerRegistry -> OpenVLA proposes action (priority 15)  
↓  
User CONFIRMS -> Authorization token issued  
↓  
ActionTranslator -> IK: OpenVLA 7D -> joint positions  
↓  
PrimitiveExecutor -> Token checked -> MuJoCo arm moves  
↓  
TrustEngine -> Success/failure -> trust update

## Key Files

| File | Purpose |
|------|---------|
| `src/external/openvla/adapter.py` | Real OpenVLA model wrapper |
| `src/external/openvla/adapter_fake.py` | Fake adapter for CI |
| `src/external/openvla/proposer_openvla.py` | ProposerBase implementation |
| `src/external/openvla/action_translator.py` | Jacobian IK solver |
| `src/external/openvla/config.yaml` | Model + action space config |
| `src/core/invariant_checker.py` | false_executions tracker |

## Safety Invariant

`false_executions == 0`

Every execution attempt is recorded by the InvariantChecker.  
The invariant is asserted:
- After every execution in debug mode
- In session summary
- In all test suites
- As a CI gate

## Running the Demo

```bash
# Interactive mode (keyboard confirm)
python scripts/run_openvla_demo.py

# Auto-confirm mode
python scripts/run_openvla_demo.py --auto-confirm --seed 42

# With metrics export
python scripts/run_openvla_demo.py --auto-confirm --export-metrics
```

## Running Tests

```bash
# All tests
pytest tests/ -v

# OpenVLA-specific tests
pytest tests/test_openvla_*.py -v

# Safety invariant tests (CRITICAL)
pytest tests/test_openvla_false_executions.py -v
pytest tests/test_invariant_checker.py -v

# Stress tests
pytest tests/test_openvla_multi_seed.py -v
pytest tests/test_openvla_stability.py -v
```
