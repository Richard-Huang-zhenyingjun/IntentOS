# Week 1: CLEAN_TABLE Intent Loop Report
Date: [Fill in completion date]

## Objective
Prove the full intent philosophy loop with deterministic heuristic planner.

## Architecture Implemented

### New Components
1. **World Builder** (`src/worlds/messy_table_world.py`)
   - Deterministic seeded table generation
   - 6 objects scattered on table
   - Bin zone marked with green circle

2. **Scene Summary** (`src/intelligence/scene_summary.py`)
   - Computes clutter score (0.0-1.0)
   - Identifies objects on table
   - Determines "messy" threshold

3. **Heuristic Proposer** (`src/intelligence/proposer_heuristic.py`)
   - Rule: If messy → propose CLEAN_TABLE
   - Deterministic, no external dependencies

4. **Plan Compiler** (`src/planning/plan_compiler.py`)
   - CLEAN_TABLE → 8 primitive sequence
   - Validates workspace bounds
   - Rejects invalid targets

5. **Primitive Executor** (`src/execution/primitive_executor.py`)
   - Multi-frame execution (Week 0 pattern)
   - Supports REACH, GRASP, MOVE_TO, RELEASE
   - State machine: IDLE → RUNNING → COMPLETE

### Integration Points
- Orchestrator now uses scene → proposer → compiler → executor pipeline
- FSM unchanged (IDLE → SELECTING → CONFIRMING → EXECUTING → DONE)
- Trust metrics preserved (false_executions == 0)

## Results

### Messy Detection Heuristic
```
Clutter score = normalized_bounding_box_area
Is messy = (n_objects >= 3) AND (clutter_score >= 0.18)
```

### Primitive Sequence (CLEAN_TABLE for 1 object)
1. REACH approach position (10cm above object)
2. REACH grasp position (2cm above object)
3. GRASP object
4. MOVE_TO lift position
5. MOVE_TO bin hover (12cm above bin)
6. MOVE_TO bin drop (3cm above bin)
7. RELEASE object
8. MOVE_TO safe home

### Test Results
```
✅ Unit tests: 11/11 passed
✅ Integration test: Object moved to bin in ~480 frames
✅ Confirm gate test: No motion without confirmation
✅ Invariant preserved: false_executions == 0
```

### Performance
- Average execution time: ~8 seconds (480 frames @ 60Hz)
- Success rate: 100% (deterministic, controlled environment)
- Objects cleaned per run: 1 (by design)

## Known Limitations

### Scope Constraints (intentional for Week 1)
- **Only 1 object** cleaned per execution
- **No multi-object** planning
- **No perception** - uses ground truth object poses
- **No recovery** - assumes perfect execution

### Technical Limitations
- Grasp assumes fixed approach angle (top-down only)
- No collision avoidance (relies on wide bin zone)
- IK may fail for objects near workspace boundary
- No dynamic re-planning if object moves

## Week 1 Definition of Done ✅

- ✅ Messy table environment builds deterministically
- ✅ Scene summary computes clutter score
- ✅ Heuristic proposer generates CLEAN_TABLE when messy
- ✅ Plan compiler produces 8-primitive sequence
- ✅ Executor runs primitives multi-frame
- ✅ Object physically moves from table to bin
- ✅ Headless integration test passes
- ✅ `false_executions == 0` invariant holds
- ✅ No Gemini, no EEG (as planned)

## Next Steps (Week 2)

### Proposed Enhancements
1. **Multi-object cleaning** - Loop until table clean
2. **Recovery behaviors** - Retry on grasp failure
3. **Collision detection** - Check workspace before motion
4. **Timing watchdogs** - Abort stuck primitives
5. **Metrics expansion** - Track success rate, time per object

### Architecture Prep for Week 3+
- Proposer interface proven ✅ (ready for Gemini integration)
- Plan compiler validation ✅ (safety gatekeeper in place)
- Executor pattern ✅ (can handle more complex primitives)

## Code Statistics
- New files: 11
- New lines of code: ~800
- Tests: 11 (unit + integration)
- Config parameters: 15

## Lessons Learned

1. **Single-object scope was correct** - Multi-object would have delayed validation
2. **Plan compiler validation essential** - Caught out-of-bounds targets in testing
3. **Multi-frame pattern from Week 0 generalizes well** - Executor reuses same pattern
4. **Fake decision source crucial for testing** - Enables deterministic integration tests

## Appendix: Example Execution Log
```
[WORLD] Created table at [0.0, 0.0, 0.3], top at z=0.6
[WORLD] Spawned 6 objects
[ORCH] Week 1 components initialized
[SCENE] Objects on table: 6, clutter_score=0.34, is_messy=True
[PROPOSER] Proposing CLEAN_TABLE (6 objects detected)
[COMPILER] Generated 8 primitives for object 5
[EXECUTOR] Started plan with 8 primitives
[EXECUTOR] Primitive 0 complete: REACH
[EXECUTOR] Primitive 1 complete: REACH
[EXECUTOR] Primitive 2 complete: GRASP
[EXECUTOR] Primitive 3 complete: MOVE_TO
[EXECUTOR] Primitive 4 complete: MOVE_TO
[EXECUTOR] Primitive 5 complete: MOVE_TO
[EXECUTOR] Primitive 6 complete: RELEASE
[EXECUTOR] Primitive 7 complete: MOVE_TO
[EXECUTOR] Plan complete!
[ORCH] Execution complete
```



