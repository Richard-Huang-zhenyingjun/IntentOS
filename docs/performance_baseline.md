# Performance Baseline (SIM-3)

Generated: 2026-02-10

## Method
- Command A (Week 7 minimal):
  - `python scripts/run_demo.py --config configs/week7_minimal.yaml --headless --profile --auto-confirm-n 5 --max-frames 400`
- Command B (Week 8 full):
  - `python scripts/run_demo.py --config configs/week8_full.yaml --headless --profile --auto-confirm-n 5 --max-frames 400`

Note: profiling was executed in headless mode to keep runs reproducible in this environment.

## Profile Summary

### Week 7 Minimal (`configs/week7_minimal.yaml`)
- Orchestrator p50: `0.58 ms`
- Overlay p50: `0.00 ms`
- Metrics p50: `0.00 ms`
- Physics/other p50: `0.02 ms`
- Total frame p50: `0.61 ms`
- Total frame p95: `1.02 ms`

### Week 8 Full (`configs/week8_full.yaml`)
- Orchestrator p50: `0.60 ms`
- Overlay p50: `0.00 ms`
- Metrics p50: `0.00 ms`
- Physics/other p50: `0.02 ms`
- Total frame p50: `0.62 ms`
- Total frame p95: `0.95 ms`

## Overhead
- p50 frame-time overhead from Week 7 -> Week 8:
  - `(0.62 - 0.61) / 0.61 = 1.64%`

Result: overhead is below the 5% threshold.

## FPS Budget Check
- Regression guard test: `tests/test_performance_regression.py`
- Condition: `p95 total frame time < 16.67 ms`
- Status: passing
