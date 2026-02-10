# Simulation Baseline Suite

## Scenarios

### Easy (seed=558)
- Objects: 5, well-spaced
- Expected success rate: >90%
- Reference metrics: `demo_artifacts/baseline_suite/easy_seed558_metrics.json`

### Medium (seed=213)
- Objects: 7-8, normal clustering
- Expected success rate: 80-90%
- Reference metrics: `demo_artifacts/baseline_suite/medium_seed213_metrics.json`

### Hard (seed=212)
- Objects: 9-10, edge cases, tight clusters
- Expected success rate: 60-80%
- Reference metrics: `demo_artifacts/baseline_suite/hard_seed212_metrics.json`

## Purpose
These scenarios form a regression baseline. Architecture changes should maintain or improve the measured metrics.
