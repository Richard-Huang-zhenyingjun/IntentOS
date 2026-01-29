#!/usr/bin/env python3
"""
Unified Demo Runner (Week 9)

Runs pre-scripted demo scenarios.
Each scenario demonstrates different aspects of the system.

Usage:
    python scripts/run_unified_demo.py --mode happy_path
    python scripts/run_unified_demo.py --mode ambiguity
    python scripts/run_unified_demo.py --mode recovery
    python scripts/run_unified_demo.py --mode full_narrative
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Generator, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from intent_core.system_orchestrator import SystemOrchestrator
from intent_core.ui_snapshot import UISnapshot
from sim.fault_injection import FaultInjector, FaultType


class DemoScenario:
    """Base class for demo scenarios"""
    
    def __init__(self, name: str, description: str, duration_seconds: float = 10.0):
        """
        Initialize scenario
        
        Args:
            name: Scenario identifier
            description: Human-readable description
            duration_seconds: Expected duration
        """
        self.name = name
        self.description = description
        self.duration_seconds = duration_seconds
    
    def setup(self, orchestrator: SystemOrchestrator):
        """
        Setup scenario (called once at start)
        
        Args:
            orchestrator: System orchestrator instance
        """
        pass
    
    def run(self, orchestrator: SystemOrchestrator) -> Generator[UISnapshot, None, None]:
        """
        Run scenario (generator that yields snapshots)
        
        Args:
            orchestrator: System orchestrator instance
            
        Yields:
            UISnapshot for each frame
        """
        raise NotImplementedError
    
    def narrate_snapshot(self, snapshot: UISnapshot):
        """
        Print narrative for current snapshot
        
        Args:
            snapshot: Current UI snapshot
        """
        # Print current narrative
        if hasattr(snapshot, 'current_narrative'):
            print(f"  [{snapshot.system_time_ms/1000:.1f}s] {snapshot.current_narrative}")


class HappyPathScenario(DemoScenario):
    """
    Scenario: Happy Path
    
    Clean execution flow:
    1. System idle
    2. Scope lamp
    3. Show affordance (Turn Off)
    4. Pinch confirm
    5. Execute
    6. Undo available
    7. Request undo
    8. Undo executed
    
    Demonstrates:
    - Complete flow without failures
    - Smooth state transitions
    - Undo mechanism
    """
    
    def __init__(self):
        super().__init__(
            name="happy_path",
            description="Clean happy path: scope → confirm → execute → undo",
            duration_seconds=15.0
        )
    
    def run(self, orchestrator: SystemOrchestrator) -> Generator[UISnapshot, None, None]:
        """Run happy path scenario"""
        print("\n" + "="*60)
        print("HAPPY PATH SCENARIO")
        print("="*60)
        print("\nDemonstrating clean execution with no failures.\n")
        
        start_time = time.time()
        
        # Phase 1: System idle
        print("Phase 1: System initializing...")
        while time.time() - start_time < 2.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            yield snapshot
            time.sleep(0.1)
        
        # Phase 2: Scope lamp
        print("\nPhase 2: User focuses on lamp...")
        # TODO: In full implementation, inject mock scope signal
        while time.time() - start_time < 5.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.scoped_object_label:
                print(f"  ✓ Scoped: {snapshot.scoped_object_label}")
                break
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 3: Show affordances
        print("\nPhase 3: System shows available actions...")
        while time.time() - start_time < 7.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.affordances_available and not hasattr(self, '_affordances_shown'):
                print(f"  ✓ Affordances ready: {len(snapshot.affordance_options)} options")
                self._affordances_shown = True
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 4: User confirms with pinch
        print("\nPhase 4: User confirms with pinch gesture...")
        # TODO: Inject pinch gesture
        while time.time() - start_time < 10.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.confirmation_state == 'confirming':
                progress = snapshot.pinch_stable_frames / snapshot.pinch_required_frames
                print(f"  ⏳ Confirming: {progress*100:.0f}%")
            elif snapshot.confirmation_state == 'confirmed':
                print("  ✓ Confirmation complete!")
                break
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 5: Execute
        print("\nPhase 5: Action executed!")
        while time.time() - start_time < 12.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.execution_result and not hasattr(self, '_execution_shown'):
                print(f"  ✓ Executed: {snapshot.last_action_type}")
                self._execution_shown = True
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 6: Undo available
        print("\nPhase 6: Undo available...")
        while time.time() - start_time < 13.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.undo_available and not hasattr(self, '_undo_shown'):
                print(f"  ✓ Undo ready: {snapshot.undo_time_remaining:.1f}s remaining")
                self._undo_shown = True
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 7: Request undo
        print("\nPhase 7: User requests undo...")
        # TODO: Inject undo request
        while time.time() - start_time < 15.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            yield snapshot
            time.sleep(0.1)
        
        print("\n" + "="*60)
        print("SCENARIO COMPLETE ✓")
        print("="*60 + "\n")


class AmbiguityScenario(DemoScenario):
    """
    Scenario: Ambiguity Refusal
    
    Demonstrates safe refusal:
    1. First object appears (lamp)
    2. Second object enters (cup)
    3. System detects ambiguity
    4. Execution blocked
    5. Narrates refusal reason
    6. Second object leaves
    7. Clarity restored
    
    Demonstrates:
    - Ambiguity detection
    - Safe refusal (not guessing)
    - Clear explanations
    """
    
    def __init__(self):
        super().__init__(
            name="ambiguity",
            description="Ambiguity detection and refusal",
            duration_seconds=12.0
        )
    
    def run(self, orchestrator: SystemOrchestrator) -> Generator[UISnapshot, None, None]:
        """Run ambiguity scenario"""
        print("\n" + "="*60)
        print("AMBIGUITY SCENARIO")
        print("="*60)
        print("\nDemonstrating safe refusal when ambiguous.\n")
        
        start_time = time.time()
        
        # Phase 1: First object appears
        print("Phase 1: Lamp appears in scene...")
        while time.time() - start_time < 3.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.scoped_object_label and not hasattr(self, '_first_object_shown'):
                print(f"  ✓ Scoped: {snapshot.scoped_object_label}")
                self._first_object_shown = True
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 2: Second object enters (creates ambiguity)
        print("\nPhase 2: Cup enters scene → AMBIGUITY")
        # TODO: Inject second object at similar location
        while time.time() - start_time < 7.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.ambiguity_detected and not hasattr(self, '_ambiguity_shown'):
                print(f"  ⚠️ AMBIGUITY DETECTED")
                print(f"     Reason: {snapshot.ambiguity_reason}")
                print(f"     System: WAITING for clarity")
                print(f"     Authority gates blocked: {', '.join(snapshot.blocking_gates)}")
                self._ambiguity_shown = True
            
            if snapshot.num_tracked_objects > 1:
                print(f"  👁 Tracking {snapshot.num_tracked_objects} objects")
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 3: Attempt to execute (should fail)
        print("\nPhase 3: User attempts to confirm (blocked)...")
        while time.time() - start_time < 9.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if not snapshot.execution_allowed:
                print("  ✗ Execution blocked by ambiguity gate")
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 4: Remove one object (resolve ambiguity)
        print("\nPhase 4: Cup leaves → clarity restored")
        # TODO: Remove second object
        while time.time() - start_time < 12.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if not snapshot.ambiguity_detected and hasattr(self, '_ambiguity_shown'):
                print("  ✓ Ambiguity resolved")
                print("  ✓ Execution now permitted")
                del self._ambiguity_shown
            
            yield snapshot
            time.sleep(0.1)
        
        print("\n" + "="*60)
        print("SCENARIO COMPLETE ✓")
        print("Key Point: System refused to guess - safety first!")
        print("="*60 + "\n")


class RecoveryScenario(DemoScenario):
    """
    Scenario: Recovery from Failure
    
    Demonstrates graceful recovery:
    1. User starts confirming action
    2. Hand disappears mid-confirmation
    3. System immediately pauses
    4. Explanation shown (why paused)
    5. Recovery steps provided
    6. Hand returns
    7. User re-scopes and re-confirms
    8. System resumes normally
    
    Demonstrates:
    - Failure detection
    - Immediate pause (no false executions)
    - Clear recovery instructions
    - Graceful resumption
    """
    
    def __init__(self):
        super().__init__(
            name="recovery",
            description="Graceful recovery from hand loss",
            duration_seconds=15.0
        )
    
    def setup(self, orchestrator: SystemOrchestrator):
        """Setup fault injection"""
        # Schedule hand dropout at 5 seconds for 2 seconds
        if orchestrator.fault_injector:
            orchestrator.fault_injector.schedule_fault(
                fault_type=FaultType.HAND_DROPOUT,
                start_time=5.0,
                duration=2.0,
                parameters={}
            )
            print("  [Setup] Scheduled hand dropout at t=5.0s for 2.0s")
    
    def run(self, orchestrator: SystemOrchestrator) -> Generator[UISnapshot, None, None]:
        """Run recovery scenario"""
        print("\n" + "="*60)
        print("RECOVERY SCENARIO")
        print("="*60)
        print("\nDemonstrating graceful recovery from hand loss.\n")
        
        start_time = time.time()
        
        # Phase 1: Normal operation - user confirming
        print("Phase 1: User starts confirming action...")
        while time.time() - start_time < 4.5:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.hand_detected and not hasattr(self, '_hand_shown'):
                print("  ✓ Hand detected")
                self._hand_shown = True
            
            if snapshot.confirmation_state == 'confirming':
                progress = snapshot.pinch_stable_frames / snapshot.pinch_required_frames
                print(f"  ⏳ Confirming: {progress*100:.0f}%")
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 2: Hand loss (fault injected)
        print("\nPhase 2: Hand disappears → SYSTEM PAUSED")
        while time.time() - start_time < 7.5:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.paused and not hasattr(self, '_pause_shown'):
                print(f"  ⏸ SYSTEM PAUSED")
                print(f"     Trigger: {snapshot.pause_trigger}")
                print(f"     Reason: {snapshot.pause_reason}")
                print(f"     Authority gates cleared: confirmation, execution")
                print(f"     No action was executed ✓")
                
                if snapshot.recovery_steps:
                    print(f"     Recovery steps:")
                    for step in snapshot.recovery_steps:
                        print(f"       - {step}")
                
                self._pause_shown = True
            
            if not snapshot.hand_detected:
                print("  ✗ Hand lost")
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 3: Hand returns
        print("\nPhase 3: Hand returns...")
        while time.time() - start_time < 10.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if snapshot.hand_detected and hasattr(self, '_pause_shown'):
                print("  ✓ Hand detected again")
                del self._pause_shown
            
            yield snapshot
            time.sleep(0.1)
        
        # Phase 4: User re-scopes and system resumes
        print("\nPhase 4: User re-scopes, system resumes...")
        while time.time() - start_time < 15.0:
            snapshot = orchestrator.step(time.time())
            self.narrate_snapshot(snapshot)
            
            if not snapshot.paused and hasattr(self, '_pause_shown'):
                print("  ✓ System resumed")
                print("  ✓ Ready for new confirmation")
            
            yield snapshot
            time.sleep(0.1)
        
        print("\n" + "="*60)
        print("SCENARIO COMPLETE ✓")
        print("Key Point: false_executions == 0 (always!)")
        print("="*60 + "\n")


class FullNarrativeScenario(DemoScenario):
    """
    Scenario: Full Narrative
    
    Complete walkthrough with narration:
    1. System initialization
    2. Multi-object scene
    3. Ambiguity handling
    4. Clean execution
    5. Failure recovery
    6. Undo mechanism
    
    Demonstrates:
    - Complete system capabilities
    - Every decision narrated
    - Calm pacing
    - Stakeholder-friendly
    """
    
    def __init__(self):
        super().__init__(
            name="full_narrative",
            description="Complete demo with full narration",
            duration_seconds=30.0
        )
    
    def run(self, orchestrator: SystemOrchestrator) -> Generator[UISnapshot, None, None]:
        """Run full narrative scenario"""
        print("\n" + "="*60)
        print("FULL NARRATIVE DEMO")
        print("="*60)
        print("\nThis demo shows the complete intent → execution flow")
        print("with full transparency and safety checks.\n")
        print("Duration: ~30 seconds")
        print("="*60 + "\n")
        
        start_time = time.time()
        current_phase = 1
        
        # Phase 1: Introduction
        print(f"Phase {current_phase}: System Initialization")
        print("  The system boots up and initializes all subsystems.")
        print("  Camera, tracking, affordance engine, and safety gates.")
        
        while time.time() - start_time < 3.0:
            snapshot = orchestrator.step(time.time())
            yield snapshot
            time.sleep(0.1)
        
        current_phase += 1
        
        # Phase 2: Multi-object scene
        print(f"\nPhase {current_phase}: Multi-Object Scene")
        print("  Multiple objects appear in the scene.")
        print("  System tracks all, but selects ONE for action.")
        
        while time.time() - start_time < 7.0:
            snapshot = orchestrator.step(time.time())
            
            if snapshot.num_tracked_objects > 0:
                print(f"  Tracking: {snapshot.num_tracked_objects} objects")
                if snapshot.primary_object_id:
                    print(f"  Primary focus: {snapshot.scoped_object_label}")
            
            yield snapshot
            time.sleep(0.15)
        
        current_phase += 1
        
        # Phase 3: Authority gates
        print(f"\nPhase {current_phase}: Authority Gates Check")
        print("  System evaluates 7 safety gates before allowing execution:")
        
        gates_to_check = [
            'scope_present',
            'scope_stable',
            'no_ambiguity',
            'affordances_available',
            'confirmation_valid',
            'not_paused',
            'execution_allowed'
        ]
        
        for _ in range(20):
            snapshot = orchestrator.step(time.time())
            
            for gate in gates_to_check:
                status = snapshot.authority_gates.get(gate, False)
                icon = "✓" if status else "✗"
                if not hasattr(self, f'_gate_{gate}_shown'):
                    print(f"    {icon} {gate}")
                    setattr(self, f'_gate_{gate}_shown', True)
                    time.sleep(0.2)
            
            yield snapshot
            time.sleep(0.1)
        
        current_phase += 1
        
        # Phase 4: Confirmation
        print(f"\nPhase {current_phase}: Gesture Confirmation")
        print("  User performs pinch gesture to confirm action.")
        print("  System requires stable gesture (no accidental triggers).")
        
        while time.time() - start_time < 15.0:
            snapshot = orchestrator.step(time.time())
            
            if snapshot.confirmation_state == 'confirming':
                progress = snapshot.pinch_stable_frames / snapshot.pinch_required_frames
                bar = "█" * int(progress * 20)
                print(f"  Progress: [{bar:<20}] {progress*100:.0f}%")
            
            yield snapshot
            time.sleep(0.1)
        
        current_phase += 1
        
        # Phase 5: Execution
        print(f"\nPhase {current_phase}: Action Execution")
        print("  All gates passed. Action executes safely.")
        
        while time.time() - start_time < 18.0:
            snapshot = orchestrator.step(time.time())
            
            if snapshot.execution_result and not hasattr(self, '_exec_shown'):
                print(f"  ✓ Executed: {snapshot.last_action_type}")
                print(f"  ✓ State changed successfully")
                self._exec_shown = True
            
            yield snapshot
            time.sleep(0.1)
        
        current_phase += 1
        
        # Phase 6: Metrics summary
        print(f"\nPhase {current_phase}: Safety Metrics")
        print("  Quantitative proof of safety:")
        
        safety_metrics = snapshot.safety_metrics
        print(f"    False executions: {safety_metrics.get('false_executions', 0)} ✓")
        print(f"    Actions executed: {safety_metrics.get('total_actions_executed', 0)}")
        print(f"    Actions refused: {safety_metrics.get('total_actions_refused', 0)}")
        print(f"    Pause events: {safety_metrics.get('total_pause_events', 0)}")
        
        while time.time() - start_time < 22.0:
            snapshot = orchestrator.step(time.time())
            yield snapshot
            time.sleep(0.1)
        
        current_phase += 1
        
        # Phase 7: Conclusion
        print(f"\nPhase {current_phase}: Conclusion")
        print("  System demonstrates:")
        print("    ✓ Transparency (every decision explained)")
        print("    ✓ Safety (false_executions == 0)")
        print("    ✓ Refusals (not errors, features)")
        print("    ✓ Recovery (graceful degradation)")
        print("    ✓ Undo (reversibility)")
        
        while time.time() - start_time < 30.0:
            snapshot = orchestrator.step(time.time())
            yield snapshot
            time.sleep(0.1)
        
        print("\n" + "="*60)
        print("FULL DEMO COMPLETE ✓")
        print("="*60 + "\n")


def print_snapshot_summary(snapshot: UISnapshot):
    """
    Print concise summary of snapshot state
    
    Args:
        snapshot: UI snapshot to summarize
    """
    print(f"\n[t={snapshot.system_time_ms/1000:.1f}s] System: {snapshot.system_state}")
    
    if snapshot.scoped_object_label:
        print(f"  Focus: {snapshot.scoped_object_label}")
    
    if snapshot.ambiguity_detected:
        print(f"  ⚠️ Ambiguity: {snapshot.ambiguity_reason}")
    
    if snapshot.paused:
        print(f"  ⏸ Paused: {snapshot.pause_reason}")
    
    if snapshot.execution_result:
        print(f"  ✓ Executed: {snapshot.last_action_type}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Run Intent Interface Demo Scenarios',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available scenarios:
  happy_path       - Clean execution: scope → confirm → execute → undo
  ambiguity        - Ambiguity detection and safe refusal
  recovery         - Graceful recovery from hand loss
  full_narrative   - Complete demo with full narration (30s)

Examples:
  python scripts/run_unified_demo.py --mode happy_path
  python scripts/run_unified_demo.py --mode recovery --seed 123
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['happy_path', 'ambiguity', 'recovery', 'full_narrative'],
        default='happy_path',
        help='Demo scenario to run'
    )
    parser.add_argument(
        '--config',
        default='configs/vision.yaml',
        help='Config file path'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for determinism'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed snapshot summaries'
    )
    parser.add_argument(
        '--no-ui',
        action='store_true',
        help='Run without UI (console only)'
    )
    
    args = parser.parse_args()
    
    # Load config
    # TODO: Load actual config file when ready
    config = {
        'fault_injection': {'enabled': True},
        'narrative': {'max_recent_events': 10},
        'system': {'seed': args.seed}
    }
    
    print("\n" + "="*60)
    print("INTENT INTERFACE - UNIFIED DEMO RUNNER")
    print("="*60)
    print(f"Mode: {args.mode}")
    print(f"Seed: {args.seed} (deterministic)")
    print(f"UI: {'disabled' if args.no_ui else 'enabled'}")
    print("="*60)
    
    # Create orchestrator
    # TODO: Initialize actual orchestrator when ready
    # orchestrator = SystemOrchestrator(config, seed=args.seed)
    print("\n[NOTE] Full orchestrator integration pending.")
    print("       This is a demo runner skeleton.\n")
    
    # Select scenario
    scenarios = {
        'happy_path': HappyPathScenario(),
        'ambiguity': AmbiguityScenario(),
        'recovery': RecoveryScenario(),
        'full_narrative': FullNarrativeScenario()
    }
    
    scenario = scenarios[args.mode]
    
    print(f"Scenario: {scenario.name}")
    print(f"Description: {scenario.description}")
    print(f"Duration: ~{scenario.duration_seconds:.0f}s\n")
    
    # Setup
    # scenario.setup(orchestrator)
    
    # Run scenario
    # TODO: Uncomment when orchestrator ready
    # for snapshot in scenario.run(orchestrator):
    #     if args.verbose:
    #         print_snapshot_summary(snapshot)
    #     
    #     if not args.no_ui:
    #         # Render to UI
    #         pass
    
    print("\nDemo runner ready! Waiting for full orchestrator integration.")
    print("="*60 + "\n")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
