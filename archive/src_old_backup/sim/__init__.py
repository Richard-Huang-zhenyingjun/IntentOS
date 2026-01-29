"""
Simulation module - fault injection and scenarios.
Week 8: Deterministic testing and demo scenarios.
Week 9: Production demo modes.
"""

from .fault_injection import FaultInjector, FaultType, ScheduledFault
from .scenarios import DemoScenario, get_scenario, list_scenarios, SCENARIOS
from .demo_modes import DemoMode, get_mode_config, get_mode_scenario, list_demo_modes

__all__ = [
    'FaultInjector',
    'FaultType',
    'ScheduledFault',
    'DemoScenario',
    'get_scenario',
    'list_scenarios',
    'SCENARIOS',
    'DemoMode',
    'get_mode_config',
    'get_mode_scenario',
    'list_demo_modes',
]

