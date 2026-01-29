# Arm Demo Script (5 Minutes)

**Hybrid BCI Robotic Control System - Complete Walkthrough**

---

## Setup (Before Demo)
```bash
# Terminal 1: Start demo in full narrative mode
python scripts/run_unified_arm_demo.py --mode full_narrative --eeg --eeg-source mock

# Wait for system initialization
# You should see: "✓ Session ID: arm_YYYYMMDD_HHMMSS"
```

---

## 0:00 - 0:30 | Introduction

**What You're Seeing:**
- PyBullet physics simulation with KUKA robot arm
- A cube on the table (target object)
- Real-time overlays showing system state

**Key Concept:**
> "This is a **permission-based** control system. The user decides **WHAT** to do (gaze selects targets, EEG confirms). The robot decides **HOW** to execute safely."

**Safety Philosophy:**
- Zero false executions (never execute without confirmation)
- Pause > partial execution
- Every refusal is explained

---

## 0:30 - 1:30 | Target Selection (Gaze-Based)

**Action**: Look at (or hover mouse over) the cube

**What Happens:**
1. System detects hover → "HOVER 50%"
2. Dwell timer starts (0.6s)
3. Lock achieved → "🔒 LOCKED TARGET"
4. State transitions: `IDLE → TARGETING → SELECTING_ACTION`

**Overlay Shows:**
```
STATE: SELECTING ACTION
TARGET: 🔒 LOCKED: Object 3
```

**Narration:**
> "Gaze-based selection eliminates the need for hand controllers. MediaPipe face tracking provides the cursor proxy. Dwell-to-lock (0.6s) prevents accidental selections."

---

## 1:30 - 2:30 | Proposal Logic (One Action at a Time)

**What Happens:**
1. World model computes available actions
2. System proposes: **MOVE_ARM_UP**
3. State: `SELECTING_ACTION → AWAITING_CONFIRM`

**Overlay Shows:**
```
PROPOSAL:
  Action: Move Arm Up
  Reason: End-effector below 0.25m (safety height)
  
Available:
  • Move Arm Up
  • Reach Forward (blocked: too low)
  • Grasp Object (blocked: not at target)
```

**Narration:**
> "The system proposes ONE action at a time based on preconditions. Notice the transparency: every blocked action has a reason. The user sees exactly what's available and why."

**Key Invariant**: Never more than one active proposal.

---

## 2:30 - 3:30 | EEG Confirmation & Autonomous Execution

**Action**: 
- **Mock EEG**: Press `C` key
- **Real BrainLink**: Sustain high attention (>70) for 1.5s

**What Happens:**
1. Decision strategy filters signal:
   - Windowing (1.5s)
   - Majority vote (67% agreement)
   - Two-hit confirm (prevents false triggers)
2. Confirmation accepted
3. State: `AWAITING_CONFIRM → EXECUTING`
4. **Robot executes autonomously**:
   - Computes IK (inverse kinematics)
   - Plans safe trajectory
   - Applies velocity/joint limits
   - Multi-frame execution (~2s)

**Overlay Shows:**
```
EXECUTING: Move Arm Up
  [████████████████░░░░] 80%
  Steps: 96/120
  
EEG (MockEEG):
  Signal: CONFIRM
  Status: STABLE ✓
```

**Narration:**
> "Once confirmed, the robot is fully autonomous. The user doesn't control joint angles or velocities—only the goal. This is shared control: user intent + robot capability."

---

## 3:30 - 4:30 | Failure Injection → Pause → Recovery

**Action** (if using `--faults` flag):

At ~3.5 minutes, fault injector triggers **EEG dropout**

**What Happens:**
1. Mid-execution, EEG signal becomes unstable
2. Safety monitor detects: `eeg_unstable_frames > grace_period`
3. System **PAUSES immediately**:
   - Robot freezes in current position
   - Overlay shows pause banner
   - State: `EXECUTING → PAUSED`

**Overlay Shows:**
```
═══════════════════════════════════
         ⚠️  SYSTEM PAUSED ⚠️        
═══════════════════════════════════
Trigger: eeg_unstable
Reason: EEG signal became unstable
Duration: 1.2s

Recovery Steps:
  1. Wait for EEG signal to stabilize
  2. Ensure good contact with headset
  3. Re-confirm action when stable

═══════════════════════════════════
```

**Narration:**
> "Notice: the robot froze immediately. No partial execution, no guessing. This is the safety philosophy: **pause > partial execution**. The system won't proceed until recovery conditions are met."

**Recovery Process:**
1. Signal stabilizes (fault ends at ~4.0s)
2. User must **unlock and re-lock target** (re-scoping)
3. System shows: "Recovery conditions met → RECOVERING"
4. After re-confirmation, execution resumes

**Key Point**: No auto-resume. User must explicitly re-engage.

---

## 4:30 - 5:00 | Trust Metrics & Takeaway

**Final Overlay State:**
```
TRUST METRICS:
  False Exec: 0 ✓ PASS
  Started: 3
  Completed: 3
  Blocked: 0
  Pauses: 1
```

**Narration:**
> "The critical metric: **False Executions = 0**. This is not an aspiration—it's an architectural guarantee. The state machine physically cannot execute without confirmation."

**Session Summary** (printed at exit):
```
TRUST & SAFETY METRICS
═══════════════════════════════════
False Executions (MUST BE 0): 0 ✓ PASS

Execution Stats:
  Started:    3
  Completed:  3
  Success Rate: 100.0%

Safety Events:
  Blocked (unstable): 0
  Pauses triggered:   1
  
Session Duration: 5.2s
═══════════════════════════════════
```

---

## Key Takeaways

1. **Permission-Based Control**
   - User: WHAT (gaze selects, EEG confirms)
   - Robot: HOW (autonomous IK execution)

2. **Safety Guarantees**
   - False executions: 0 (provable)
   - Pause > partial execution
   - No auto-resume

3. **Transparency**
   - Every proposal explained
   - Every blocked action has a reason
   - All metrics visible in real-time

4. **Robustness**
   - EEG dropout → immediate pause
   - Recovery requires explicit re-engagement
   - Trust metrics tracked throughout

---

## Commands Reference
```bash
# Happy path (no faults)
python scripts/run_unified_arm_demo.py --mode happy_path

# Safety refusal (high variance blocks confirmation)
python scripts/run_unified_arm_demo.py --mode safety_refusal --eeg --eeg-source mock

# Recovery demonstration (EEG dropout mid-execution)
python scripts/run_unified_arm_demo.py --mode recovery --eeg --eeg-source mock --faults

# Full 5-minute narrative
python scripts/run_unified_arm_demo.py --mode full_narrative --eeg --eeg-source mock

# Real BrainLink Lite
python scripts/run_unified_arm_demo.py --mode happy_path --eeg --eeg-source brainlink

# Generate metrics report
python scripts/generate_arm_metrics_report.py --latest --format markdown,console
```

---

## Technical Details

**Architecture:**
- **Week 1-2**: Physics simulation + world model
- **Week 3**: Gaze-based target selection
- **Week 4**: State machine + orchestration
- **Week 5**: IK solver + trajectory planning
- **Week 6**: Grasping physics
- **Week 7**: Real BrainLink EEG integration
- **Week 8**: Safety monitor + recovery controller
- **Week 9**: Production demo infrastructure

**Papers Implemented:**
- MDPI "Hybrid BCI for Robotic Arm Control" (core control loop)
- MediaPipe face mesh (gaze proxy)
- PyBullet IK solver (autonomous execution)

---

**End of Demo Script**




