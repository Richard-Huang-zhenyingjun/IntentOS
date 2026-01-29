"""
Demo modes - pre-configured demonstration scenarios.
Week 9: Production-ready demo infrastructure.
"""

from enum import Enum
from typing import Dict, Any, Optional
from .scenarios import get_scenario, DemoScenario


class DemoMode(str, Enum):
    """
    Demo mode identifiers.
    
    Each mode showcases specific system capabilities:
    - HAPPY_PATH: Normal operation end-to-end
    - SAFETY_REFUSAL: System blocks unsafe actions
    - RECOVERY: Pause and recovery workflow
    - FULL_NARRATIVE: Complete 5-minute walkthrough
    """
    HAPPY_PATH = "happy_path"
    SAFETY_REFUSAL = "safety_refusal"
    RECOVERY = "recovery"
    FULL_NARRATIVE = "full_narrative"


def get_mode_config(mode: DemoMode, base_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get configuration for demo mode.
    
    Args:
        mode: Demo mode
        base_cfg: Base configuration dict
        
    Returns:
        Updated configuration for mode
    """
    cfg = base_cfg.copy()
    
    if mode == DemoMode.HAPPY_PATH:
        # Normal operation, no faults
        cfg['demo']['print_narrative'] = True
        cfg['faults']['enabled'] = False
        scenario = None
        
    elif mode == DemoMode.SAFETY_REFUSAL:
        # High variance blocks confirmation
        cfg['demo']['print_narrative'] = True
        cfg['faults']['enabled'] = True
        scenario = get_scenario("high_variance_blocks")
        cfg['faults']['schedule'] = scenario.faults
        
    elif mode == DemoMode.RECOVERY:
        # EEG dropout mid-execution → pause → recover
        cfg['demo']['print_narrative'] = True
        cfg['faults']['enabled'] = True
        scenario = get_scenario("eeg_dropout_mid_reach")
        cfg['faults']['schedule'] = scenario.faults
        
    elif mode == DemoMode.FULL_NARRATIVE:
        # Complete walkthrough with narration
        cfg['demo']['print_narrative'] = True
        cfg['demo']['auto_advance_narrative'] = True
        cfg['faults']['enabled'] = True
        scenario = get_scenario("happy_path")  # Start with happy path
        cfg['faults']['schedule'] = []
    
    return cfg


def get_mode_scenario(mode: DemoMode) -> Optional[DemoScenario]:
    """
    Get scenario for demo mode.
    
    Args:
        mode: Demo mode
        
    Returns:
        DemoScenario or None
    """
    scenario_map = {
        DemoMode.HAPPY_PATH: "happy_path",
        DemoMode.SAFETY_REFUSAL: "high_variance_blocks",
        DemoMode.RECOVERY: "eeg_dropout_mid_reach",
        DemoMode.FULL_NARRATIVE: "happy_path",
    }
    
    scenario_name = scenario_map.get(mode)
    if scenario_name:
        return get_scenario(scenario_name)
    return None


def list_demo_modes() -> list[str]:
    """Get list of available demo modes."""
    return [mode.value for mode in DemoMode]




