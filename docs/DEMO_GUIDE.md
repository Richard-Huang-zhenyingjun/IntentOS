# Intent Interface Demo Guide

**Complete guide for running and presenting the Intent Interface demo.**

Version: 1.0 (Week 9)  
Last Updated: 2024

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Demo Modes](#demo-modes)
3. [UI Layout](#ui-layout)
4. [Recording the Demo](#recording-the-demo)
5. [Presentation Tips](#presentation-tips)
6. [Troubleshooting](#troubleshooting)
7. [FAQ](#faq)
8. [Advanced Usage](#advanced-usage)

---

## Quick Start

### Installation

```bash
# Clone repository
git clone [repository-url]
cd intent-interface-prototype

# Install dependencies
pip install -r requirements.txt

# Verify installation
pytest tests/ -v
```

### Run Your First Demo

```bash
# Happy path demo (2-3 minutes)
python scripts/run_unified_demo.py --mode happy_path

# Full narrative demo (5-7 minutes)
python scripts/run_unified_demo.py --mode full_narrative --seed 42

# Generate metrics report
python scripts/generate_metrics_report.py

# Replay session with explanation
python scripts/replay_session.py logs/session_latest.jsonl --explain
```

---

## Demo Modes

### 1. Happy Path (`happy_path`)

**Duration:** 2-3 minutes  
**Purpose:** Show clean execution flow  
**Best for:** Quick demos, initial introductions, time-constrained presentations

**Flow:**
1. System initializes in IDLE state
2. User focuses on lamp → Scope acquired
3. Affordances appear (Turn Off, Toggle)
4. User pinches to confirm → Progress bar fills
5. Action executes → Lamp state changes
6. Undo becomes available (10s window)
7. User requests undo → Pinch to confirm
8. Action reversed

**Key Teaching Points:**
- Affordances are READ-ONLY predictions
- Explicit confirmation required
- Undo requires same rigor as execution
- `false_executions == 0` maintained

**Command:**
```bash
python scripts/run_unified_demo.py --mode happy_path
```

---

### 2. Ambiguity (`ambiguity`)

**Duration:** 2-3 minutes  
**Purpose:** Demonstrate safe refusal when uncertain  
**Best for:** Showing trust through transparency, safety-focused audiences

**Flow:**
1. First object (lamp) appears → Scoped
2. Second object (cup) enters scene
3. **Ambiguity detected** → Authority gate fails
4. System refuses to guess (51/49 choice avoided)
5. UI shows: "Multiple objects competing - waiting for clarity"
6. Affordances blocked
7. Second object removed
8. Ambiguity clears → System resumes

**Key Teaching Points:**
- System never guesses when uncertain
- Authority gate "No Ambiguity" must pass
- Refusals are features, not bugs
- Transparency builds trust

**Command:**
```bash
python scripts/run_unified_demo.py --mode ambiguity --seed 42
```

---

### 3. Recovery (`recovery`)

**Duration:** 3-4 minutes  
**Purpose:** Graceful failure handling and recovery  
**Best for:** Showing robustness, demonstrating fault tolerance

**Flow:**
1. User starts confirming action
2. Pinch progress: 3/6 frames
3. **Hand disappears** (fault injected at 5.0s)
4. System immediately **PAUSES**
5. Confirmation state cleared
6. Recovery instructions displayed:
   - "Ensure hand is visible"
   - "Re-establish scope"
   - "Re-confirm action"
7. Hand returns → User re-scopes
8. System transitions: PAUSED → RECOVERING → SCOPED
9. User must re-confirm to execute

**Key Teaching Points:**
- Immediate pause on failure
- No false executions during failures
- Clear recovery instructions
- Requires re-confirmation (no shortcuts)

**Command:**
```bash
python scripts/run_unified_demo.py --mode recovery --seed 42
```

---

### 4. Full Narrative (`full_narrative`)

**Duration:** 5-7 minutes  
**Purpose:** Complete walkthrough with all features  
**Best for:** Stakeholder presentations, investor demos, comprehensive overviews

**Flow:**
1. **Phase 1:** System initialization (30s)
2. **Phase 2:** Multi-object scene (60s)
   - Tracks multiple objects
   - Selects ONE for action
3. **Phase 3:** Authority gates check (60s)
   - Shows all 7 gates sequentially
   - Explains pass/fail for each
4. **Phase 4:** Gesture confirmation (60s)
   - Pinch detection
   - Stable gesture requirement
   - Progress visualization
5. **Phase 5:** Action execution (30s)
   - All gates pass
   - Safe execution
6. **Phase 6:** Safety metrics (30s)
   - Shows quantitative proof
   - `false_executions == 0`
7. **Phase 7:** Conclusion (30s)
   - Key principles summary
   - Transparency message

**Key Teaching Points:**
- Complete system capabilities
- Every decision explained
- Quantitative safety proof
- Comprehensive narrative

**Command:**
```bash
python scripts/run_unified_demo.py --mode full_narrative --seed 42
```

---

## UI Layout

### Screen Layout (Recommended: Split-Screen)

```
┌────────────────────────────────────┬────────────────────────────────────┐
│                                    │  ╔══════════════════════════════╗  │
│                                    │  ║   SYSTEM STATUS              ║  │
│                                    │  ╚══════════════════════════════╝  │
│         CAMERA FEED                │  🎯 STATE: SCOPED                 │
│      (with overlays)               │  Status: Ready to act on lamp     │
│                                    │                                    │
│  ┌──────────────────────────┐     │  ╔══════════════════════════════╗  │
│  │  [Lamp]                  │     │  ║   RECENT EVENTS              ║  │
│  │   Green bbox             │     │  ╚══════════════════════════════╝  │
│  │   (scoped)               │     │  t=12.3  🎯  Focused on lamp      │
│  │                          │     │  t=12.9  ✨  Actions available    │
│  └──────────────────────────┘     │  t=13.1  👆  Confirming...        │
│                                    │  t=13.5  ✓   Confirmed!           │
│  Center reticle: ⊕                │  t=13.6  ▶️  Executed action      │
│                                    │                                    │
│  Status: "Pinch to confirm"       │  ╔══════════════════════════════╗  │
│                                    │  ║   AUTHORITY GATES            ║  │
│                                    │  ╚══════════════════════════════╝  │
│                                    │  ✓ Scope Present                  │
│                                    │  ✓ Scope Stable                   │
│                                    │  ✓ No Ambiguity                   │
│                                    │  ✓ Affordances Available          │
│                                    │  ✗ Confirmation Valid             │
│                                    │     → Gesture not complete        │
│                                    │  ✓ System Active                  │
│                                    │  ✗ Execution Allowed              │
│                                    │                                    │
│                                    │  ╔══════════════════════════════╗  │
│                                    │  ║   SCENE STATUS               ║  │
│                                    │  ╚══════════════════════════════╝  │
│                                    │  👁 1 object tracked              │
│                                    │  Focus: lamp                      │
│                                    │                                    │
│                                    │  ╔══════════════════════════════╗  │
│                                    │  ║   AFFORDANCES (READ-ONLY)    ║  │
│                                    │  ╚══════════════════════════════╝  │
│                                    │  Object State: ON (conf=0.85)     │
│                                    │  Method: visual_heuristic         │
│                                    │                                    │
│                                    │  Predicted Actions (2):           │
│                                    │  ► 1. Turn Off (conf=0.85)        │
│                                    │    2. Toggle Power (conf=0.75)    │
│                                    │                                    │
│                                    │  ⚠️ These are predictions         │
│                                    │     Execution requires confirm    │
│                                    │                                    │
│                                    │  ╔══════════════════════════════╗  │
│                                    │  ║   CONFIRMATION               ║  │
│                                    │  ╚══════════════════════════════╝  │
│                                    │  ✓ Hand detected (conf=0.92)      │
│                                    │  👆 Pinch: 4/6 (67%)              │
│                                    │     [████████████░░░░░░░░]         │
│                                    │  ⏳ CONFIRMING...                 │
│                                    │                                    │
│                                    │  ╔══════════════════════════════╗  │
│                                    │  ║   RECOVERY & UNDO            ║  │
│                                    │  ╚══════════════════════════════╝  │
│                                    │  ✓ System active                  │
│                                    │                                    │
│                                    │  ↩️ Undo available:               │
│                                    │    toggle_power on lamp           │
│                                    │    Expires in 8.2s                │
└────────────────────────────────────┴────────────────────────────────────┘
```

### Key UI Elements

**Camera Feed Overlays:**
- Object bounding boxes (color-coded by state)
- Center reticle (⊕)
- Scope indicator (green highlight)
- Pause banner (red, full-width)
- Status text at bottom

**Intent Panel (7 Sections):**
1. **System Status** - Current state, emoji icon, reason
2. **Recent Events** - Last 5 events with timestamps and icons
3. **Authority Gates** - 7-gate checklist with ✓/✗ and reasons
4. **Scene Status** - Object count, focus, ambiguity warnings
5. **Affordances** - State estimate + predicted actions (READ-ONLY)
6. **Confirmation** - Hand/pinch detection + progress bar
7. **Recovery & Undo** - Pause info, undo availability

---

## Recording the Demo

### Equipment Needed

**Hardware:**
- **Camera:** Webcam or phone camera (720p minimum, 1080p recommended)
- **Computer:** Runs system + screen recording
- **Microphone:** For narration (headset or standalone)
- **Lighting:** Good ambient lighting for camera

**Software:**
- **Screen Recording:** OBS Studio, QuickTime, or built-in recorder
- **Video Editing:** DaVinci Resolve, iMovie, or Premiere Pro
- **Audio Editing:** Audacity (if separate audio track)

### Pre-Recording Checklist

```bash
# 1. Clean environment
rm -rf logs/*
mkdir -p logs

# 2. Test camera
python scripts/test_camera.py

# 3. Verify all components
pytest tests/test_final_trust_regressions.py -v

# 4. Test full demo
python scripts/run_unified_demo.py --mode full_narrative --seed 42

# 5. Check UI rendering
# Visual inspection: all 7 sections visible?

# 6. Verify metrics collection
python scripts/generate_metrics_report.py --summary
```

### Recording Steps

**Step 1: Setup**
```bash
# Clear desktop (minimize distractions)
# Close unnecessary applications
# Set display to presentation mode
# Open terminal at correct directory
# Position camera to see scene
```

**Step 2: Record**
```bash
# Start screen recording software

# Option A: Run demo mode (scripted)
python scripts/run_unified_demo.py --mode full_narrative --seed 42

# Option B: Run interactive (manual control)
python src/main.py --demo-mode

# Narrate live or record voice separately
# Follow demo_script_5min.md

# Stop recording when demo completes
```

**Step 3: Post-Processing**
```bash
# Generate metrics report
python scripts/generate_metrics_report.py --format html --output demo_report.html

# Create replay video (optional)
python scripts/replay_session.py logs/session_latest.jsonl --explain > replay.log

# Edit video:
# - Add intro slide (5s)
# - Trim dead time
# - Add captions for key moments
# - Overlay metrics at end (10s)
# - Add outro with contact info (5s)
# - Export: 1080p, 30fps, H.264
```

### Video Structure (Recommended)

```
0:00 - 0:05   Intro slide (logo, title, tagline)
0:05 - 0:30   Introduction (narrator + system overview)
0:30 - 1:30   Happy path demo
1:30 - 2:30   Ambiguity refusal demo
2:30 - 3:30   Recovery demo
3:30 - 4:15   Undo demo
4:15 - 5:00   Metrics + conclusion
5:00 - 5:10   Outro slide (contact, links)
```

---

## Presentation Tips

### Before Presenting

**Day Before:**
- [ ] Test full demo 3x times
- [ ] Record backup video
- [ ] Prepare slides (if using)
- [ ] Print script as backup reference
- [ ] Charge laptop fully
- [ ] Test projector/display connection

**Morning Of:**
- [ ] Test demo once more
- [ ] Clear desktop (professional appearance)
- [ ] Close unnecessary programs
- [ ] Set display resolution (1080p recommended)
- [ ] Silence phone and notifications
- [ ] Have water nearby

**Right Before:**
- [ ] Breathe deeply (calm nerves)
- [ ] Run system in demo mode
- [ ] Check camera feed quality
- [ ] Verify UI rendering correctly
- [ ] One final test gesture
- [ ] Begin with confidence!

### During Presentation

**Pacing:**
- Speak slowly and clearly
- Pause after each key point
- Give audience time to read UI
- Don't rush through refusals (they're important!)

**Visual Aids:**
- Use laser pointer or cursor to highlight
- Zoom in on authority gates when explaining
- Point to narrative events as they appear
- Show progress bars filling in real-time

**Emphasis Points:**
- "This is a **refusal**, not an error"
- "Notice: **zero false executions**"
- "Affordances are **READ-ONLY predictions**"
- "System **waits** for clarity"
- "**Explicit confirmation** required"

**Body Language:**
- Make eye contact with audience
- Stand confidently
- Gesture to screen when explaining
- Don't just read from screen
- Show enthusiasm!

**Handling Issues:**
- If live demo fails → switch to backup video
- If question during demo → pause and answer
- If technical glitch → explain, move on
- Stay calm and professional

### After Presenting

**Immediate Follow-Up:**
- Open for questions
- Show metrics report if requested
- Offer to replay specific sections
- Share screen if helpful

**Materials to Share:**
- Metrics report (HTML)
- Session logs (for technical audience)
- Demo video (if recorded)
- Documentation links
- Code repository access
- Contact information

---

## Troubleshooting

### Demo Won't Start

**Symptom:** Script fails to run

**Solutions:**
```bash
# Check Python version (3.8+ required)
python --version

# Install dependencies
pip install -r requirements.txt

# Verify config files exist
ls -la configs/

# Test in isolation
pytest tests/test_system_orchestrator.py -v

# Check for import errors
python -c "from src.intent_core.system_orchestrator import SystemOrchestrator"
```

---

### Camera Not Detecting Objects

**Symptom:** No bounding boxes appear

**Solutions:**
```bash
# Test camera directly
python scripts/test_camera.py

# Check camera permissions (macOS/Linux)
# System Preferences → Security & Privacy → Camera

# Lower detection threshold
# Edit configs/vision.yaml:
# detection:
#   min_confidence: 0.5  # Lower from 0.7

# Verify lighting conditions
# Ensure good ambient light

# Try mock mode (for testing)
# configs/vision.yaml:
# camera:
#   mock_mode: true
```

---

### UI Not Updating

**Symptom:** Intent panel frozen or blank

**Solutions:**
```bash
# Check if process running
ps aux | grep intent_visualizer

# Restart with verbose logging
python src/main.py --verbose --debug

# Check UI dependencies
pip install tkinter pillow

# Verify display environment variable (Linux)
echo $DISPLAY

# Try Week 9 visualizer directly
python -c "from src.ui.intent_visualizer_week9 import IntentVisualizerWeek9; print('OK')"
```

---

### Metrics Report Empty

**Symptom:** Report shows zero events

**Solutions:**
```bash
# Verify metrics collection enabled
grep 'metrics' configs/*.yaml

# Check log files exist
ls -la logs/
cat logs/session_latest.jsonl

# Run with metrics enabled explicitly
python scripts/run_unified_demo.py --mode happy_path --metrics

# Generate report with verbose output
python scripts/generate_metrics_report.py --verbose
```

---

### Session Replay Fails

**Symptom:** replay_session.py errors

**Solutions:**
```bash
# Check log file format
head -1 logs/session_xyz.jsonl
# Should be valid JSON

# Try with different log file
ls logs/
python scripts/replay_session.py logs/session_123.jsonl

# Run with verbose errors
python scripts/replay_session.py logs/session_xyz.jsonl --verbose

# Validate JSON
python -m json.tool logs/session_xyz.jsonl > /dev/null
```

---

## FAQ

### General Questions

**Q: Can I run the demo without a camera?**  
A: Yes! Use simulated/mock mode:
```bash
# Edit configs/vision.yaml:
camera:
  mock_mode: true

# Or run demo with simulation
python scripts/run_unified_demo.py --mode happy_path --simulated
```

**Q: How long does a typical demo take?**  
A: 
- Quick demo (happy_path): 2-3 minutes
- Focused demo (ambiguity or recovery): 3-4 minutes
- Full narrative: 5-7 minutes
- With Q&A: 10-15 minutes total

**Q: What's the best demo for a 5-minute investor pitch?**  
A: Use `full_narrative` mode or combine `happy_path` + `ambiguity`:
```bash
# Option 1: Full narrative (comprehensive)
python scripts/run_unified_demo.py --mode full_narrative

# Option 2: Custom combination
# Show happy_path, then manually trigger ambiguity
```

**Q: Can I customize the demo script?**  
A: Yes! Edit the scenario classes in `scripts/run_unified_demo.py`:
```python
class MyCustomScenario(DemoScenario):
    def __init__(self):
        super().__init__(name="my_demo", description="Custom flow")
    
    def run(self, orchestrator):
        # Your custom demo logic here
        pass
```

### Technical Questions

**Q: How do I prove safety guarantees to a skeptical audience?**  
A: Show the metrics report live:
```bash
# After demo, generate report
python scripts/generate_metrics_report.py

# Key metrics to highlight:
# - false_executions = 0
# - unauthorized_executions = 0
# - Refusal rate (shows caution)
# - Recovery completion rate
```

**Q: Can I replay a specific session?**  
A: Yes, sessions are logged to `logs/` directory:
```bash
# List available sessions
ls -lt logs/

# Replay with explanation
python scripts/replay_session.py logs/session_12345.jsonl --explain

# Step through frame-by-frame
python scripts/replay_session.py logs/session_12345.jsonl --step
```

**Q: How do I capture the demo for later viewing?**  
A: Multiple options:
```bash
# Option 1: Screen recording (manual)
# Use OBS Studio or QuickTime

# Option 2: Session logs (automatic)
# Logs saved to logs/ directory automatically

# Option 3: Generate replay video from logs
python scripts/replay_session.py logs/session.jsonl --explain > replay.txt
# Then create video from replay.txt
```

**Q: What if the live demo fails during a presentation?**  
A: Three-tier backup plan:
1. **Pre-recorded video** - Play backup video (identical demo)
2. **Session replay** - Use replay script with logs
3. **Static walkthrough** - Use screenshots + narration

Always have backup video ready!

**Q: How do I demonstrate determinism?**  
A: Run with same seed twice:
```bash
# Run 1
python scripts/run_unified_demo.py --mode happy_path --seed 42 > run1.log

# Run 2
python scripts/run_unified_demo.py --mode happy_path --seed 42 > run2.log

# Compare (should be identical)
diff run1.log run2.log
```

---

## Advanced Usage

### Custom Fault Injection

Create custom failure scenarios:

```python
# Edit configs/vision.yaml or create custom config
fault_injection:
  enabled: true
  fault_schedule:
    - type: "hand_dropout"
      start_time: 3.5
      duration: 2.0
    - type: "object_loss"
      start_time: 8.0
      duration: 1.0
    - type: "ambiguity_burst"
      start_time: 12.0
      duration: 3.0
```

### Live Metrics Display

Show metrics in real-time during demo:

```bash
# Terminal 1: Run demo
python scripts/run_unified_demo.py --mode full_narrative

# Terminal 2: Watch metrics (updates every second)
watch -n 1 'python scripts/generate_metrics_report.py --summary'
```

### Multi-Language Support

Generate reports in different formats:

```bash
# HTML report (for sharing)
python scripts/generate_metrics_report.py --format html --output report.html

# Text report (for console)
python scripts/generate_metrics_report.py --format text --output report.txt

# Summary only (for quick checks)
python scripts/generate_metrics_report.py --summary
```

### Batch Demo Generation

Generate multiple demo recordings:

```bash
#!/bin/bash
# demo_batch.sh

for seed in 42 123 456 789; do
    echo "Recording demo with seed $seed..."
    python scripts/run_unified_demo.py --mode full_narrative --seed $seed
    python scripts/generate_metrics_report.py --output "report_$seed.html"
done
```

---

## Support & Resources

### Documentation
- **Full specification:** `docs/Week_1-9_Specification.md`
- **Demo script:** `docs/demo_script_5min.md`
- **Architecture:** `docs/Architecture.md`
- **API reference:** `docs/API.md`

### Code
- **Demo runner:** `scripts/run_unified_demo.py`
- **Metrics generator:** `scripts/generate_metrics_report.py`
- **Session replay:** `scripts/replay_session.py`
- **Test suite:** `tests/test_final_trust_regressions.py`

### Logs & Output
- **Session logs:** `logs/session_*.jsonl`
- **Metrics reports:** `metrics_report.txt` or `.html`
- **Replay transcripts:** Generated on-demand

### Getting Help

**For technical issues:**
- Check troubleshooting section above
- Review test suite: `pytest tests/ -v`
- Check logs: `tail -f logs/session_latest.jsonl`

**For demo questions:**
- Review `docs/demo_script_5min.md`
- Watch example videos (if available)
- Practice with `--step` mode

**For contributions:**
- See `CONTRIBUTING.md` (if available)
- Submit issues to repository
- Propose improvements via pull requests

---

## Quick Reference Card

**Essential Commands:**
```bash
# Run demos
python scripts/run_unified_demo.py --mode [MODE]

# Generate reports
python scripts/generate_metrics_report.py

# Replay sessions
python scripts/replay_session.py logs/[FILE] --explain

# Test system
pytest tests/ -v

# Check safety
python scripts/generate_metrics_report.py --summary
```

**Demo Modes:**
- `happy_path` - Clean execution (2-3 min)
- `ambiguity` - Safe refusal (2-3 min)
- `recovery` - Failure handling (3-4 min)
- `full_narrative` - Complete demo (5-7 min)

**Key Metrics:**
- `false_executions` - MUST be 0
- `unauthorized_executions` - MUST be 0
- `refusal_rate` - Shows caution
- `recovery_completion_rate` - Shows robustness

---

**Demo Guide Version 1.0 - Week 9**  
**Last Updated: 2024**  
**Status: Production Ready**






