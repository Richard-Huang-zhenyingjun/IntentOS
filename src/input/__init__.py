"""
Input module - user decision signals.
Week 4: Keyboard (C/X keys).
Week 6: EEG interface + MockEEG.
Week 7: BrainLink Lite integration + decision strategy.
"""

from .confirm_input import KeyboardConfirmInput
from .eeg_interface import EEGDecisionSource
from .mock_eeg import MockEEG
from .decision_strategy import DecisionStrategy, DecisionMeta
from .signal_quality import SignalWindow, SignalQualityReport, compute_stability
from .brainlink import BrainLinkDecisionSource

__all__ = [
    'KeyboardConfirmInput',
    'EEGDecisionSource',
    'MockEEG',
    'DecisionStrategy',
    'DecisionMeta',
    'SignalWindow',
    'SignalQualityReport',
    'compute_stability',
    'BrainLinkDecisionSource',
]
