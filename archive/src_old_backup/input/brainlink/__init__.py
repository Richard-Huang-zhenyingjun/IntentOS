"""
BrainLink integration package.
Week 7: BrainLink Lite serial communication and EEG processing.
"""

from .brainlink_client import BrainLinkClient, BrainLinkSample
from .brainlink_decoder import BrainLinkFeatures, decode_sample
from .brainlink_decision import BrainLinkDecisionSource

__all__ = [
    'BrainLinkClient',
    'BrainLinkSample',
    'BrainLinkFeatures',
    'decode_sample',
    'BrainLinkDecisionSource',
]

