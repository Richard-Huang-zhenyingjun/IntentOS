# Intent Interface Demo Script (5 Minutes)

**Audience:** Investors, researchers, general technical audience  
**Goal:** Prove the system is trustworthy through transparency  
**Key Message:** "The system understands what you want — and proves it by refusing to act when it shouldn't."

---

## Setup (Before Demo Starts)

### Hardware
- Camera positioned to see scene
- Lamp, door (or representations), phone visible
- Hand in view for gesture detection
- System running in demo mode (deterministic seed)

### Software
- UI visible on screen (split-screen recommended)
  - **Left:** Camera feed with overlays (640x480)
  - **Right:** Intent visualization panel (7 sections)
- Logs recording to file
- Metrics collector running

### Pre-Check
- [ ] System in IDLE state
- [ ] All Week 1-9 components loaded
- [ ] Camera feed visible
- [ ] UI rendering correctly
- [ ] Test pinch gesture works
- [ ] Backup video ready

---

## Script

### **[0:00 - 0:30] Introduction (30 seconds)**

**Narrator:**  
"This is the Intent Interface — a brain-computer interface prototype that lets you control your environment with thought and gesture. But here's what makes it different: **it refuses to act when it shouldn't — and it explains why.**"

**Show on Screen:**
- System in IDLE state
- Empty scene or neutral position
- UI showing:
  - System Status: IDLE
  - Authority Gates: Most red (scope not present)
  - Narrative: "System ready. Waiting for input."

**Pointer:**  
"Notice the 7-section interface on the right. This shows you *everything* the system is thinking — in real-time."

**Key Point:**  
"Transparency builds trust. Let's prove it."

---

### **[0:30 - 1:30] Happy Path: Clean Execution (60 seconds)**

**Narrator:**  
"Let's start with the happy path. Watch what happens when I focus on the lamp."

#### **[0:30 - 0:45] Scope Acquisition (15s)**

**Actions:**
1. User looks at lamp
2. System detects lamp (green bounding box appears)
3. Scope stabilizes after ~5 frames

**UI Updates:**
- System Status: IDLE → SCOPED
- Scope section: "🎯 Focused: lamp (85% confidence)"
- Authority Gates:
  - ✓ Scope Present: PASS
  - ✓ Scope Stable: PASS
  - ✓ No Ambiguity: PASS

**Narrator:**  
"The system detected my attention on the lamp. Notice the confidence level — 85%. It knows what I'm looking at."

#### **[0:45 - 1:00] Affordance Generation (15s)**

**UI Updates:**
- Affordances section appears:
  - Object State: OFF (conf=0.85)
  - Method: visual_heuristic
  - Predicted Actions (2):
    1. turn_off (conf=0.85)
    2. toggle_power (conf=0.75)
  - ⚠️ **These are predictions, not decisions**
  - Execution requires explicit confirmation

**Narrator:**  
"The system predicted I want to turn off the lamp. **But notice** — it hasn't done anything yet. This is a prediction, not a decision. The affordances are clearly labeled as READ-ONLY."

**Pointer:**  
"See the authority gates checklist — most are green now, but 'Confirmation Valid' is still red. The system needs my explicit confirmation."

#### **[1:00 - 1:30] Confirmation & Execution (30s)**

**Actions:**
1. User pinches (thumb + index finger)
2. Pinch stability check begins

**UI Updates:**
- Confirmation section:
  - ✓ Hand detected (conf=0.92)
  - 👆 Pinch: 1/6 (17%)
  - Progress bar: [███░░░░░░░░░░░░░░░░░]
  - ⏳ CONFIRMING...

**Narrator:**  
"I'm pinching to confirm. The system requires 6 stable frames — about 0.2 seconds — to prevent accidental triggers. Watch the progress bar."

**UI Updates:**
- Progress: 2/6... 3/6... 4/6... 5/6... 6/6
- Confirmation section: ✓ CONFIRMED
- Authority Gates:
  - ✓ Confirmation Valid: PASS → (turns green)
  - ✓ Execution Allowed: PASS

**Actions:**
4. Lamp state changes (OFF → ON or visual indicator)

**UI Updates:**
- System Status: SCOPED → EXECUTING → SCOPED
- Narrative Timeline:
  - "▶️ Executed: toggle_power on lamp → off → on"
- Undo section: "↩️ Undo available: toggle_power on lamp (9.8s remaining)"

**Narrator:**  
"Action executed. Notice the system waited for my explicit confirmation — it **never assumed**. And now undo is available for 10 seconds."

---

### **[1:30 - 2:30] Refusal 1: Ambiguity (60 seconds)**

**Narrator:**  
"Now let's see what happens when the system **isn't sure** what I want."

#### **[1:30 - 1:50] Ambiguity Detection (20s)**

**Actions:**
1. Second object (cup) enters scene near lamp
2. System detects both objects
3. Ambiguity triggered

**UI Updates:**
- Scene Status:
  - 👁 2 objects tracked
  - Focus: None
  - ⚠️ AMBIGUITY
  - Multiple objects (2) competing for focus - waiting for clarity

- Authority Gates:
  - ✓ Scope Present: PASS
  - ✗ No Ambiguity: FAIL → (turns red)
  - ✗ Execution Allowed: FAIL
  - Blocked by: no_ambiguity

- Camera Feed:
  - Both objects have bounding boxes
  - No object highlighted (both faint yellow)

**Narrator:**  
"The system sees two objects close together and **refuses to guess** which one I want. This is a **feature, not a bug**. It won't make a 51/49 choice."

**Pointer:**  
"Look at the authority gates — 'No Ambiguity' failed and turned red. The system explains exactly why it's waiting."

#### **[1:50 - 2:10] Waiting for Clarity (20s)**

**Actions:**
1. User attempts to pinch (optional, to show blocking)

**UI Updates:**
- Affordances section: "❌ Blocked: ambiguity detected"
- Narrative Timeline:
  - "⚠️ Multiple objects competing - waiting for clarity"
- No confirmation progress (blocked)

**Narrator:**  
"Even if I try to confirm, nothing happens. The system won't execute when it's uncertain. **Safety over speed.**"

#### **[2:10 - 2:30] Resolution (20s)**

**Actions:**
1. Cup removed from scene (or moved far away)
2. Ambiguity clears

**UI Updates:**
- Scene Status:
  - 👁 1 object tracked
  - Focus: lamp
  - ✓ Ambiguity resolved

- Authority Gates:
  - ✓ No Ambiguity: PASS → (turns green)

- Affordances re-appear

**Narrator:**  
"When clarity returns, the system continues normally. No guessing, no assumptions — just waiting for me to make my intent clear."

---

### **[2:30 - 3:30] Refusal 2: Failure Recovery (60 seconds)**

**Narrator:**  
"What if something goes wrong **during** confirmation?"

#### **[2:30 - 2:50] Failure Triggered (20s)**

**Actions:**
1. User focuses on lamp (scoped)
2. User starts confirming with pinch
3. Pinch progress: 1/6... 2/6... 3/6...
4. **Hand moves out of view** (or fault injected)

**UI Updates:**
- Confirmation section:
  - 👆 Pinch: 3/6 (50%)
  - ✗ Hand not detected → (hand lost)

- System Status: CONFIRMING → PAUSED

- Recovery & Undo section:
  - ⏸ SYSTEM PAUSED
  - Trigger: hand_loss
  - Reason: Hand lost during confirmation
  - Recovery required

**Camera Feed:**
- Red "PAUSED" banner overlay
- Scene frozen visually

**Narrator:**  
"The system detected hand loss during confirmation and **paused immediately**. No action was executed. Zero false executions — always."

#### **[2:50 - 3:10] Recovery Instructions (20s)**

**UI Updates:**
- Recovery section shows:
  - Recovery Steps:
    1. Ensure hand is visible
    2. Re-establish object in view
    3. Confirm action again
  - Explanation: "Hand lost during confirmation. No action executed. Re-scope and re-confirm to resume."

- Authority Gates:
  - ✗ Confirmation Valid: FAIL (cleared by pause)
  - ✗ System Active: FAIL (paused)
  - ✗ Execution Allowed: FAIL

**Narrator:**  
"The system explains **exactly** what happened and **how to recover**. It cleared the confirmation state — I must re-confirm. No shortcuts."

**Pointer:**  
"This is graceful degradation. The system stays in a safe state until I fix the problem."

#### **[3:10 - 3:30] Recovery Complete (20s)**

**Actions:**
1. Hand returns to view
2. User re-focuses on lamp
3. System transitions: PAUSED → RECOVERING → SCOPED

**UI Updates:**
- System Status: PAUSED → RECOVERING → SCOPED
- Narrative Timeline:
  - "🔄 Recovery initiated"
  - "✅ Recovery complete. System resumed."
  - "🎯 Focused: lamp"

- Authority Gates:
  - ✓ System Active: PASS → (turns green)
  - (Confirmation still red until re-confirmed)

**Narrator:**  
"The system requires me to re-establish intent and re-confirm. **Same rigor as before.** Trust through consistency."

---

### **[3:30 - 4:15] Undo (45 seconds)**

**Narrator:**  
"Finally, the system supports undo — but with the **same rigor** as initial execution."

#### **[3:30 - 3:50] Undo Available (20s)**

**UI Updates:**
- Recovery & Undo section:
  - ✓ System active
  - ↩️ Undo available: toggle_power on lamp
  - Expires in 8.3s... 8.2s... 8.1s...

**Narrator:**  
"After the previous execution, undo became available for 10 seconds. There's a countdown — it expires to prevent stale undos."

**Pointer:**  
"Notice undo is a first-class feature, not an afterthought. It's tracked, timed, and requires confirmation."

#### **[3:50 - 4:05] Undo Request (15s)**

**Actions:**
1. User presses 'U' key (or specific gesture)
2. System enters UNDO_CONFIRMING state

**UI Updates:**
- System Status: SCOPED → UNDO_CONFIRMING
- Recovery & Undo section:
  - ↩️ Undo requested: toggle_power on lamp
  - ⏳ CONFIRMING UNDO...

**Narrator:**  
"I requested undo. But notice — the system doesn't just do it. It requires confirmation, **just like the original action**."

#### **[4:05 - 4:15] Undo Execution (10s)**

**Actions:**
1. User pinches to confirm undo
2. Pinch progress: 1/6... 6/6
3. Lamp state restores (ON → OFF)

**UI Updates:**
- Confirmation section: ✓ CONFIRMED
- Lamp state changes back
- Narrative Timeline:
  - "↩️ Undone: toggle_power on lamp"
  - "State restored to previous"

**Narrator:**  
"Undo executed. **Symmetry builds trust** — same confirmation flow for both actions and undos."

---

### **[4:15 - 5:00] Conclusion & Safety Proof (45 seconds)**

**Narrator:**  
"Let's look at the **safety metrics** from this session."

**Show on Screen:**
- Metrics panel appears (overlay or side panel):

```
═══════════════════════════════════════════════
SAFETY GUARANTEES
═══════════════════════════════════════════════
✓ false_executions = 0 (PASS)
✓ unauthorized_executions = 0 (PASS)

🎉 ALL SAFETY GUARANTEES MET 🎉

═══════════════════════════════════════════════
TRUST METRICS
═══════════════════════════════════════════════
Ambiguity Waits: 1
  → System waited for clarity instead of guessing

Pause Triggers: 1
  → System paused safely when failure detected

Recovery Completions: 1
  → 100% of pauses recovered successfully

═══════════════════════════════════════════════
EXECUTION SUMMARY
═══════════════════════════════════════════════
Executions: 2
Refusals: 2
Undos: 1

→ 50% refusal rate (safety-first approach)
```

**Narrator:**  
"**Zero false executions.** Zero unauthorized actions. Every refusal explained. Every pause recovered gracefully. **This is quantitative proof of safety.**"

**Pointer:**  
"Notice the refusal rate — 50%. That's not a bug, it's the system being **appropriately cautious**."

**Final Visual:**
- Split screen showing:
  - **Left:** Authority Gates checklist (all green in final state)
  - **Right:** Narrative timeline showing complete flow
- Tagline appears: **"Transparent. Safe. Trustworthy."**

**Narrator (Final Message):**  
"The Intent Interface proves it's trustworthy by showing you **every decision it makes** — and **every decision it refuses to make**. Transparency isn't optional. It's the foundation."

**Closing:**
"Thank you. Questions?"

---

## Technical Notes

### Timing Breakdown
| Section | Duration | Content |
|---------|----------|---------|
| Introduction | 0:30 | System overview, key message |
| Happy Path | 1:00 | Scope → Affordances → Confirm → Execute |
| Ambiguity Refusal | 1:00 | Multi-object → Wait → Resolve |
| Recovery | 1:00 | Failure → Pause → Recover |
| Undo | 0:45 | Request → Confirm → Execute |
| Conclusion | 0:45 | Metrics, safety proof, message |
| **TOTAL** | **5:00** | |

### Key Visuals (Always On-Screen)

**Left Panel (Camera Feed):**
- Live video with overlays
- Bounding boxes for tracked objects
- Scope indicator (green for focused)
- Pause banner when paused

**Right Panel (Intent Visualization - 7 Sections):**
1. **System Status** - Current state with emoji icon
2. **Recent Events** - Last 5 narrative events with icons
3. **Authority Gates** - 7-gate checklist with ✓/✗
4. **Scene Status** - Object count, focus, ambiguity
5. **Affordances (READ-ONLY)** - Predicted actions
6. **Confirmation** - Hand/pinch progress
7. **Recovery & Undo** - Current issues, undo status

### Demo Tips

**Before Demo:**
- [ ] Test full flow once
- [ ] Verify camera positioning
- [ ] Check lighting
- [ ] Practice narration timing
- [ ] Have backup video ready

**During Demo:**
- **Pace calmly** - No rushed transitions
- **Point to UI elements** - Help audience follow
- **Emphasize refusals** - They're features, not bugs
- **Show confidence** - You've tested this
- **Make eye contact** - Don't just read screen

**Visual Aids:**
- Use laser pointer or cursor to highlight sections
- Zoom in on authority gates during key moments
- Show metrics panel dramatically at end

### Backup Plan (If Live Demo Fails)

**Option 1: Pre-recorded Video**
- Have identical demo pre-recorded
- Same script, same timing
- Switch seamlessly: "Let me show you a recording..."

**Option 2: Replay Mode**
- Use `replay_session.py --explain`
- Show logged session with narration
- Proves determinism: "This is from an earlier run..."

**Option 3: Static Walkthrough**
- Use screenshots with annotations
- Walk through each step
- Show metrics report
- Less impressive but still proves architecture

### Questions to Anticipate

**Q: "How does it know what I'm looking at?"**  
**A:** "Object detection using a camera feed, combined with visual saliency. In Week 1-2, we implemented camera-based object tracking. A full BCI would use gaze estimation or neural signals, but the *decision architecture* stays the same."

**Q: "What if I change my mind?"**  
**A:** "You can cancel confirmation by releasing the pinch. Undo is available for 10 seconds after execution. And you can always just don't confirm — the system waits indefinitely."

**Q: "How do you prevent false executions?"**  
**A:** "Multiple authority gates — 7 checks that all must pass. We log every event and can prove `false_executions == 0` from the metrics. The system is designed to fail safe."

**Q: "Is this practical for real use?"**  
**A:** "This is a research prototype demonstrating **safe intent execution architecture**. Real deployment would optimize frame rates and reduce confirmation time, but the **safety architecture stays the same**. Speed vs. safety is a tunable tradeoff."

**Q: "Can it handle complex scenes?"**  
**A:** "Week 7 added multi-object robustness — up to 10 objects with ambiguity detection and oscillation suppression. We showed 2 objects today for clarity, but the system handles more."

**Q: "What about privacy?"**  
**A:** "All processing is local. Camera data never leaves the device. Logs are local JSONL files. No cloud, no tracking. Week 9 deliverable includes full replay from local logs."

**Q: "What happens if the camera fails?"**  
**A:** "Camera failure triggers a safe pause, just like hand loss. The system explains what happened and waits. No execution during degraded states."

**Q: "How long did this take to build?"**  
**A:** "9 weeks of incremental development, each week adding a layer of safety and functionality. ~4,700 lines of production code for Week 9 components alone. Full system is deterministic and replay-able."

**Q: "Can I see the code?"**  
**A:** "Yes, it's fully documented. The architecture is modular — you can inspect any component. Week 9 includes comprehensive tests proving all invariants."

**Q: "What's next?"**  
**A:** "Multi-user identity (Week 10+), adaptive learning, AR/MR integration. But first, we're publishing the safety architecture and seeking collaborators."

---

## Presentation Variants

### **3-Minute Version** (Condensed)
- Introduction: 0:20
- Happy Path: 0:40
- Ambiguity OR Recovery: 0:40 (pick one)
- Conclusion: 0:40
- Skip undo section

### **10-Minute Version** (Extended)
- Add detailed authority gate walkthrough
- Show live metrics during demo
- Demonstrate replay system
- Show HTML report generation
- Include Q&A preparation time

### **30-Second Elevator Pitch**
"Intent interfaces let you control things with thought and gesture. But how do you trust them? We built a system that **proves** it's safe by refusing to act when uncertain — and explaining every decision in real-time. Zero false executions, always."

---

## Post-Demo Materials to Share

1. **Metrics Report (HTML)**
   - Generated from session
   - Shows quantitative safety proof
   - Professional, shareable

2. **Replay Video with Explanation**
   - Run `replay_session.py --explain`
   - Record the output
   - Shows determinism

3. **Architecture Documentation**
   - Week 1-9 progression
   - Authority gates explanation
   - Safety invariants list

4. **Code Repository Access**
   - GitHub link (if public)
   - Installation instructions
   - Test suite commands

---

## Final Checklist

**Day Before:**
- [ ] Test full demo 3x times
- [ ] Record backup video
- [ ] Prepare slides (if using)
- [ ] Print script as backup
- [ ] Charge laptop fully
- [ ] Test projector/display

**Morning Of:**
- [ ] Test demo once more
- [ ] Clear desktop (minimize distractions)
- [ ] Close unnecessary programs
- [ ] Set display to presentation mode
- [ ] Silence phone/notifications
- [ ] Have water nearby

**Right Before:**
- [ ] Breathe deeply
- [ ] Run system in demo mode
- [ ] Check camera feed
- [ ] Verify UI rendering
- [ ] One final test pinch
- [ ] Begin with confidence

---

## Success Criteria

**Audience Should Leave Understanding:**
1. The system makes predictions (read-only affordances)
2. Execution requires explicit confirmation
3. Refusals are explained transparently
4. Failures trigger safe pauses with recovery
5. Metrics prove safety quantitatively
6. The architecture is trustworthy by design

**Emotional Impact:**
- Impressed by transparency
- Reassured by safety measures
- Curious to learn more
- Confident in the approach

**Call to Action:**
- Request metrics report
- Ask for code access
- Propose collaboration
- Schedule follow-up meeting

---

## Contact Information (Include in Closing Slide)

**Intent Interface Project**  
[Your Institution/Company]  
[Project Website]  
[Contact Email]  
[GitHub Repository]

**For more information:**
- Technical documentation: [Link]
- Research paper: [Link if published]
- Demo videos: [Link]
- Collaboration inquiries: [Email]

---

**END OF DEMO SCRIPT**

*Last Updated: [Date]*  
*Version: 1.0 - Week 9 Final Demo*




