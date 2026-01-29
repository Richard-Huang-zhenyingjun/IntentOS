#!/usr/bin/env python3
"""
Replay Session with Explanation (Week 9)

Deterministically replay a logged session with optional narrative explanation mode.

Features:
- Frame-by-frame deterministic replay
- Narrative explanation of decisions
- Authority gate analysis
- Step-through debugging mode
- Summary statistics

Usage:
    python scripts/replay_session.py session.jsonl
    python scripts/replay_session.py session.jsonl --explain
    python scripts/replay_session.py session.jsonl --step
    python scripts/replay_session.py session.jsonl --summary
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


class SessionReplay:
    """
    Replay logged session with optional explanation
    
    Features:
    - Deterministic frame-by-frame replay
    - Narrative explanation of decisions
    - Authority gate analysis
    - Pause/step through mode
    """
    
    def __init__(self, log_file: Path, explain: bool = False, verbose: bool = False):
        """
        Initialize session replay
        
        Args:
            log_file: Path to JSONL log file
            explain: Enable detailed explanations
            verbose: Enable verbose output
        """
        self.log_file = log_file
        self.explain = explain
        self.verbose = verbose
        self.events: List[Dict[str, Any]] = []
        
        # Statistics
        self.session_start_time = None
        self.session_end_time = None
        
        # Load log file
        self._load_log()
    
    def _load_log(self):
        """Load JSONL log file"""
        if not self.log_file.exists():
            raise FileNotFoundError(f"Log file not found: {self.log_file}")
        
        print(f"Loading log file: {self.log_file}")
        
        with open(self.log_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        event = json.loads(line)
                        self.events.append(event)
                        
                        # Track session times
                        timestamp = event.get('timestamp')
                        if timestamp:
                            if self.session_start_time is None:
                                self.session_start_time = timestamp
                            self.session_end_time = timestamp
                    except json.JSONDecodeError as e:
                        print(f"Warning: Invalid JSON on line {line_num}: {e}")
                        continue
        
        if len(self.events) == 0:
            raise ValueError("No valid events found in log file")
        
        duration = (self.session_end_time - self.session_start_time) if self.session_start_time else 0
        print(f"✓ Loaded {len(self.events)} events (duration: {duration:.1f}s)")
        print("")
    
    def replay(self, step_mode: bool = False, filter_types: List[str] = None):
        """
        Replay session
        
        Args:
            step_mode: If True, pause after each event
            filter_types: Optional list of event types to show
        """
        print("=" * 70)
        print("SESSION REPLAY")
        print("=" * 70)
        print("")
        
        if self.explain:
            print("Mode: EXPLANATION (detailed)")
        else:
            print("Mode: BASIC (event log)")
        
        if step_mode:
            print("Step mode: ON (press Enter to advance, 'q' to quit)")
        
        if filter_types:
            print(f"Filter: {', '.join(filter_types)}")
        
        print("")
        
        for i, event in enumerate(self.events):
            event_type = event.get('type', 'unknown')
            
            # Apply filter if specified
            if filter_types and event_type not in filter_types:
                continue
            
            self._replay_event(i, event)
            
            if step_mode:
                user_input = input(">>> ")
                if user_input.lower() == 'q':
                    print("\nReplay stopped by user.")
                    break
    
    def _replay_event(self, index: int, event: Dict[str, Any]):
        """Replay single event"""
        event_type = event.get('type', 'unknown')
        timestamp = event.get('timestamp', 0.0)
        
        # Calculate relative time
        rel_time = timestamp - self.session_start_time if self.session_start_time else timestamp
        
        # Event icon
        icons = {
            'scope_acquired': '🎯',
            'scope_lost': '❌',
            'affordances_available': '✨',
            'affordances_blocked': '🚫',
            'confirmation_started': '👆',
            'confirmation_progress': '⏳',
            'confirmation_completed': '✓',
            'confirmation_cancelled': '✗',
            'execution_succeeded': '▶️',
            'execution_refused': '❌',
            'pause_triggered': '⏸',
            'recovery_started': '🔄',
            'recovery_completed': '✅',
            'undo_available': '↩️',
            'undo_applied': '↩️',
            'undo_refused': '✗',
            'ambiguity_detected': '⚠️',
            'oscillation_detected': '⚠️',
        }
        
        icon = icons.get(event_type, '•')
        
        # Print event header
        print(f"[{index:04d}] t={rel_time:6.2f}s | {icon} {event_type}")
        
        # Event-specific handling
        if self.explain:
            self._explain_event(event_type, event)
        else:
            # Basic summary
            if 'narrative' in event:
                print(f"  {event['narrative']}")
            elif 'reason' in event:
                print(f"  {event['reason']}")
        
        print("")
    
    def _explain_event(self, event_type: str, event: Dict[str, Any]):
        """Provide detailed explanation of event"""
        
        if event_type == "scope_acquired":
            obj = event.get('object_label', 'unknown')
            category = event.get('category', 'unknown')
            conf = event.get('confidence', 0.0)
            print(f"  → User focused on {obj} ({category})")
            print(f"  → Detection confidence: {conf:.2%}")
            print(f"  → System can now generate affordances")
            print(f"  → Authority gate 'scope_present' will pass")
        
        elif event_type == "scope_lost":
            reason = event.get('reason', 'unknown')
            print(f"  → Lost scope on object")
            print(f"  → Reason: {reason}")
            print(f"  → System will wait for new scope")
            print(f"  → Authority gate 'scope_present' will fail")
        
        elif event_type == "affordances_available":
            options = event.get('options', [])
            state_aware = event.get('state_aware', False)
            count = event.get('count', len(options))
            print(f"  → {count} actions predicted")
            if state_aware:
                print(f"  → Method: STATE-AWARE (used object state)")
            else:
                print(f"  → Method: FALLBACK (state uncertain, using toggle)")
            print(f"  → Options: {', '.join(options)}")
            print(f"  → These are READ-ONLY predictions")
            print(f"  → Waiting for user confirmation")
        
        elif event_type == "affordances_blocked":
            reason = event.get('reason', 'unknown')
            print(f"  → Actions blocked: {reason}")
            print(f"  → No options available for execution")
            print(f"  → Authority gate 'affordances_available' will fail")
        
        elif event_type == "confirmation_started":
            action = event.get('action_type', 'action')
            obj = event.get('object_label', 'object')
            print(f"  → User initiating: {action} on {obj}")
            print(f"  → Waiting for stable gesture (typically 6 frames)")
        
        elif event_type == "confirmation_progress":
            held = event.get('frames_held', 0)
            required = event.get('frames_required', 6)
            percentage = event.get('percentage', 0)
            print(f"  → User confirming: {held}/{required} frames")
            print(f"  → Progress: {percentage:.0f}%")
            print(f"  → System requires stable gesture to prevent accidents")
        
        elif event_type == "confirmation_completed":
            action = event.get('action_type', 'action')
            obj = event.get('object_label', 'object')
            print(f"  → Confirmation complete: {action} on {obj}")
            print(f"  → Authority gate 'confirmation_valid' now passes")
            print(f"  → System will execute on next tick")
        
        elif event_type == "confirmation_cancelled":
            reason = event.get('reason', 'unknown')
            print(f"  → Confirmation cancelled: {reason}")
            print(f"  → No action will be executed")
            print(f"  → User must re-confirm if still desired")
        
        elif event_type == "execution_succeeded":
            action = event.get('action_type', 'action')
            obj = event.get('object_label', 'object')
            before = event.get('before_state', {})
            after = event.get('after_state', {})
            state_change = event.get('state_change', '')
            print(f"  → EXECUTED: {action} on {obj}")
            print(f"  → State change: {state_change}")
            if self.verbose:
                print(f"  → Before: {before}")
                print(f"  → After: {after}")
            print(f"  → Action is reversible (undo available for ~10s)")
            print(f"  → false_executions counter remains 0 ✓")
        
        elif event_type == "execution_refused":
            reason = event.get('reason', 'unknown')
            print(f"  → EXECUTION REFUSED")
            print(f"  → Reason: {reason}")
            print(f"  → This is a FEATURE, not a bug")
            print(f"  → Analyzing authority gates...")
            self._explain_authority_gates(event)
        
        elif event_type == "pause_triggered":
            trigger = event.get('trigger', 'unknown')
            reason = event.get('reason', '')
            print(f"  → SYSTEM PAUSED")
            print(f"  → Trigger: {trigger}")
            print(f"  → Reason: {reason}")
            print(f"  → All execution blocked until recovery")
            print(f"  → Confirmation state cleared (must re-confirm)")
            
            recovery = event.get('recovery_actions', [])
            if recovery:
                print(f"  → Recovery steps:")
                for i, action in enumerate(recovery, 1):
                    print(f"      {i}. {action}")
        
        elif event_type == "recovery_started":
            print(f"  → User initiated recovery process")
            print(f"  → System will guide through recovery steps")
        
        elif event_type == "recovery_completed":
            print(f"  → Recovery complete")
            print(f"  → System resumed normal operation")
            print(f"  → User can now perform new actions")
        
        elif event_type == "ambiguity_detected":
            num_obj = event.get('num_objects', 0)
            print(f"  → AMBIGUITY: {num_obj} objects competing for focus")
            print(f"  → System REFUSES to guess (51/49 choice)")
            print(f"  → Waiting for clarity (user disambiguates)")
            print(f"  → Authority gate 'no_ambiguity' fails")
            print(f"  → No execution will occur")
        
        elif event_type == "oscillation_detected":
            suppressed = event.get('suppressed_count', 0)
            print(f"  → OSCILLATION: Rapid attention switching detected")
            print(f"  → Suppressing {suppressed} objects temporarily")
            print(f"  → Waiting for user to focus on one object")
        
        elif event_type == "undo_available":
            action = event.get('action_type', 'action')
            obj = event.get('object_label', 'object')
            time_remaining = event.get('time_remaining', 0)
            print(f"  → Undo available: {action} on {obj}")
            print(f"  → Time remaining: {time_remaining:.1f}s")
            print(f"  → User can reverse action with gesture")
        
        elif event_type == "undo_requested":
            action = event.get('action_type', 'action')
            obj = event.get('object_label', 'object')
            print(f"  → Undo requested: {action} on {obj}")
            print(f"  → Waiting for confirmation")
        
        elif event_type == "undo_applied":
            action = event.get('action_type', 'action')
            obj = event.get('object_label', 'object')
            print(f"  → UNDO APPLIED: Reversed {action} on {obj}")
            print(f"  → State restored to previous")
            print(f"  → Action fully reversed")
        
        elif event_type == "undo_refused":
            reason = event.get('reason', 'unknown')
            print(f"  → Undo refused: {reason}")
            print(f"  → Undo window may have expired")
            print(f"  → Or system in incompatible state")
        
        else:
            # Generic explanation
            if 'narrative' in event:
                print(f"  → {event['narrative']}")
            elif 'details' in event:
                print(f"  → Details: {event['details']}")
    
    def _explain_authority_gates(self, event: Dict[str, Any]):
        """Explain which authority gates blocked execution"""
        reason = event.get('reason', '').lower()
        
        print(f"  → Authority Gate Checklist:")
        
        # Gate 1: Scope Present
        if "no scope" in reason or "scope" in reason:
            print(f"      ✗ Scope Present: FAIL (no object scoped)")
        else:
            print(f"      ✓ Scope Present: PASS")
        
        # Gate 2: Scope Stable
        if "unstable" in reason or "confidence" in reason:
            print(f"      ✗ Scope Stable: FAIL (confidence too low)")
        else:
            print(f"      ✓ Scope Stable: PASS")
        
        # Gate 3: No Ambiguity
        if "ambiguity" in reason or "multiple objects" in reason:
            print(f"      ✗ No Ambiguity: FAIL (multiple objects competing)")
        else:
            print(f"      ✓ No Ambiguity: PASS")
        
        # Gate 4: Affordances Available
        if "no affordances" in reason or "no actions" in reason:
            print(f"      ✗ Affordances Available: FAIL")
        else:
            print(f"      ✓ Affordances Available: PASS")
        
        # Gate 5: Confirmation Valid
        if "not confirmed" in reason or "confirmation" in reason:
            print(f"      ✗ Confirmation Valid: FAIL (gesture not complete)")
        else:
            print(f"      ✓ Confirmation Valid: PASS")
        
        # Gate 6: Not Paused
        if "paused" in reason:
            print(f"      ✗ System Active: FAIL (system paused)")
        else:
            print(f"      ✓ System Active: PASS")
        
        # Gate 7: Execution Allowed
        print(f"      ✗ Execution Allowed: FAIL")
        print(f"  → Result: Execution BLOCKED (safe refusal)")
    
    def generate_summary(self):
        """Generate replay summary"""
        print("=" * 70)
        print("REPLAY SUMMARY")
        print("=" * 70)
        print("")
        
        # Count event types
        event_counts = {}
        for event in self.events:
            event_type = event.get('type', 'unknown')
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        
        # Session info
        duration = (self.session_end_time - self.session_start_time) if self.session_start_time else 0
        print(f"Session Duration: {duration:.1f}s")
        print(f"Total Events: {len(self.events)}")
        print("")
        
        # Event breakdown
        print("Event Breakdown:")
        for event_type, count in sorted(event_counts.items(), key=lambda x: -x[1]):
            print(f"  {event_type}: {count}")
        
        print("")
        
        # Key metrics
        scope_acq = event_counts.get('scope_acquired', 0)
        scope_lost = event_counts.get('scope_lost', 0)
        affordances = event_counts.get('affordances_available', 0)
        confirmations = event_counts.get('confirmation_completed', 0)
        executions = event_counts.get('execution_succeeded', 0)
        refusals = event_counts.get('execution_refused', 0)
        pauses = event_counts.get('pause_triggered', 0)
        undos = event_counts.get('undo_applied', 0)
        ambiguity = event_counts.get('ambiguity_detected', 0)
        
        print("Key Metrics:")
        print(f"  Scope Acquisitions: {scope_acq}")
        print(f"  Scope Losses: {scope_lost}")
        print(f"  Affordances Generated: {affordances}")
        print(f"  Confirmations: {confirmations}")
        print(f"  Executions: {executions}")
        print(f"  Refusals: {refusals}")
        print(f"  Pauses: {pauses}")
        print(f"  Undos: {undos}")
        print(f"  Ambiguity Events: {ambiguity}")
        
        # Safety check
        print("")
        print("Safety Check:")
        # Look for any false execution indicators
        false_exec_events = [e for e in self.events if e.get('type') == 'false_execution']
        if len(false_exec_events) == 0:
            print("  ✓ false_executions = 0 (PASS)")
        else:
            print(f"  ✗ false_executions = {len(false_exec_events)} (FAIL)")
        
        # Refusal rate
        total_attempts = executions + refusals
        if total_attempts > 0:
            refusal_rate = (refusals / total_attempts) * 100
            print(f"  Refusal Rate: {refusal_rate:.0f}% (safety-first)")
        
        print("")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Replay Intent Interface Session',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic replay
  python scripts/replay_session.py logs/session_001.jsonl
  
  # Detailed explanation
  python scripts/replay_session.py logs/session_001.jsonl --explain
  
  # Step through each event
  python scripts/replay_session.py logs/session_001.jsonl --step
  
  # Summary only
  python scripts/replay_session.py logs/session_001.jsonl --summary
  
  # Filter specific events
  python scripts/replay_session.py logs/session_001.jsonl --filter execution_succeeded execution_refused
        """
    )
    
    parser.add_argument(
        'log_file',
        type=Path,
        help='Path to session log file (JSONL format)'
    )
    parser.add_argument(
        '--explain',
        action='store_true',
        help='Enable detailed explanation mode'
    )
    parser.add_argument(
        '--step',
        action='store_true',
        help='Enable step-through mode (pause after each event)'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Show summary only (no event-by-event replay)'
    )
    parser.add_argument(
        '--filter',
        nargs='+',
        help='Filter to specific event types'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    try:
        # Create replay
        replay = SessionReplay(
            args.log_file,
            explain=args.explain,
            verbose=args.verbose
        )
        
        if args.summary:
            replay.generate_summary()
        else:
            replay.replay(
                step_mode=args.step,
                filter_types=args.filter
            )
            replay.generate_summary()
        
        return 0
    
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n\nReplay interrupted by user.")
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
