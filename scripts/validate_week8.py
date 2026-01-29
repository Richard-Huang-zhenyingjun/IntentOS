#!/usr/bin/env python3
"""
Week 8 Validation Script
Validates all Week 8 components and generates trust report.
"""

import sys
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.robotics.recovery import (
    RecoveryController, RecoveryState, PauseTrigger,
    UndoController, FaultInjector, FaultType,
    TrustMetricsTracker
)


def validate_configuration():
    """Validate Week 8 configuration."""
    print("\n" + "="*60)
    print("VALIDATING CONFIGURATION")
    print("="*60)
    
    cfg = yaml.safe_load(open('configs/robotics.yaml'))
    
    # Check recovery config
    assert 'recovery' in cfg, "Missing recovery config"
    recovery_cfg = cfg['recovery']
    
    required_keys = ['enable', 'pause_on', 'target_loss_grace_frames', 
                     'eeg_unstable_grace_frames', 'rest_pose', 'undo']
    for key in required_keys:
        assert key in recovery_cfg, f"Missing recovery config key: {key}"
    
    print("✅ Recovery configuration valid")
    
    # Check faults config
    assert 'faults' in cfg, "Missing faults config"
    faults_cfg = cfg['faults']
    
    required_keys = ['enabled', 'seed', 'schedule']
    for key in required_keys:
        assert key in faults_cfg, f"Missing faults config key: {key}"
    
    print("✅ Faults configuration valid")
    
    return cfg


def validate_recovery_controller(cfg):
    """Validate RecoveryController."""
    print("\n" + "="*60)
    print("VALIDATING RECOVERY CONTROLLER")
    print("="*60)
    
    rc = RecoveryController(cfg['recovery'])
    
    # Test initialization
    assert rc.enabled is True
    assert rc.target_loss_grace == 10
    assert rc.eeg_unstable_grace == 30
    print("✅ RecoveryController initialized correctly")
    
    # Test grace period
    for i in range(29):
        result = rc.check_eeg_stable(False)
        assert result is True
    print("✅ Grace period working (29 frames no pause)")
    
    # Test pause trigger
    result = rc.check_eeg_stable(False)
    assert result is False
    assert rc.is_paused
    print("✅ Pause triggered after grace period")
    
    # Test status
    status = rc.get_status()
    assert status.state == RecoveryState.PAUSED
    assert status.trigger == PauseTrigger.EEG_UNSTABLE
    assert len(status.explanation) > 0
    print(f"✅ Status: {status.explanation}")
    
    # Test reset
    rc.reset()
    assert not rc.is_paused
    print("✅ Reset working")


def validate_undo_controller(cfg):
    """Validate UndoController."""
    print("\n" + "="*60)
    print("VALIDATING UNDO CONTROLLER")
    print("="*60)
    
    uc = UndoController(cfg['recovery'])
    
    assert uc.enable_return_to_rest is True
    assert uc.detach_before_rest is True
    assert not uc.is_active()
    print("✅ UndoController initialized correctly")
    
    # Test reset
    uc.active = True
    uc.reset()
    assert not uc.is_active()
    print("✅ Reset working")


def validate_fault_injector(cfg):
    """Validate FaultInjector."""
    print("\n" + "="*60)
    print("VALIDATING FAULT INJECTOR")
    print("="*60)
    
    fi = FaultInjector(cfg['faults'])
    fi.enabled = True
    
    # Schedule fault
    fi.schedule_fault(FaultType.EEG_DROPOUT, trigger_frame=10, duration_frames=5)
    assert len(fi.schedule) == 1
    print("✅ Fault scheduling working")
    
    # Test activation
    for frame in range(10):
        fi.tick(frame)
        assert not fi.should_inject_eeg_dropout()
    
    fi.tick(10)
    assert fi.should_inject_eeg_dropout()
    print("✅ Fault activation working")
    
    # Test deactivation
    fi.tick(15)
    assert not fi.should_inject_eeg_dropout()
    print("✅ Fault deactivation working")
    
    # Check log
    log = fi.get_injection_log()
    assert len(log) >= 2
    print(f"✅ Injection log: {len(log)} events")


def validate_trust_metrics():
    """Validate TrustMetricsTracker."""
    print("\n" + "="*60)
    print("VALIDATING TRUST METRICS")
    print("="*60)
    
    tracker = TrustMetricsTracker()
    
    # Record events
    tracker.record_execution("MOVE_ARM_UP", confirmed=True, success=True)
    tracker.record_execution("REACH_FORWARD", confirmed=True, success=True)
    tracker.record_pause(PauseTrigger.EEG_UNSTABLE, "EEG signal unstable")
    tracker.record_recovery()
    tracker.record_execution("GRASP_OBJECT", confirmed=True, success=True)
    
    print("✅ Event recording working")
    
    # Generate report
    report = tracker.generate_report()
    
    assert report.false_executions == 0
    assert report.confirmed_executions == 3
    assert report.pauses_triggered == 1
    assert report.pauses_recovered == 1
    assert report.all_refusals_explained is True
    
    print("✅ Report generation working")
    
    # Check safety guarantee
    report_dict = report.to_dict()
    assert report_dict["safety_metrics"]["safety_guarantee"] == "PASS"
    print("✅ Safety guarantee: PASS")
    
    # Print summary
    tracker.print_summary()
    
    return report


def main():
    """Run all validations."""
    print("\n" + "="*60)
    print("WEEK 8 VALIDATION")
    print("="*60)
    
    try:
        # Validate components
        cfg = validate_configuration()
        validate_recovery_controller(cfg)
        validate_undo_controller(cfg)
        validate_fault_injector(cfg)
        report = validate_trust_metrics()
        
        # Final summary
        print("\n" + "="*60)
        print("VALIDATION COMPLETE ✅")
        print("="*60)
        print("\nAll Week 8 components validated successfully!")
        print("\nKey Results:")
        print(f"  - RecoveryController: ✅ Working")
        print(f"  - UndoController: ✅ Working")
        print(f"  - FaultInjector: ✅ Working")
        print(f"  - TrustMetricsTracker: ✅ Working")
        print(f"  - Safety Guarantee: ✅ PASS (false_executions = 0)")
        print("\n" + "="*60)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ VALIDATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())




