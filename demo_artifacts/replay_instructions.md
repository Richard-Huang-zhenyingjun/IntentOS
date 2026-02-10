# How to Replay Demo Session

## Option 1: Event Replay

```bash
python scripts/replay_session.py demo_artifacts/demo_run_seed42_events.jsonl
```

Alternative compact replay:

```bash
python -m src.tools.replay_events demo_artifacts/demo_run_seed42_events.jsonl
```

## Option 2: Deterministic Re-run

```bash
python scripts/run_demo.py --seed 42
# Follow the same control flow: L (lock), C (confirm), Q (quit)
```

## Expected Output

- Session starts with deterministic world seed `42`.
- Authorization token issue/complete events appear in the event stream.
- Safety invariant remains intact: `false_executions == 0`.
- Trust remains stable for this recorded run (`1.00` to `1.00`).
