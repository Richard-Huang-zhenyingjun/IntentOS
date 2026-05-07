"""EEG signal acquisition and decoding."""

from src.input.eeg.eeg_source import EEGSample, EEGSource
from src.input.eeg.decision_source import EEGDecisionSource
from src.input.eeg.types import EEGWindow, EEGFeatures
from src.input.eeg.ring_buffer import EEGRingBuffer
from src.input.eeg.device_replay import ReplayDevice
from src.input.eeg.device_brainlink import BrainLinkDevice
from src.input.eeg.eeg_source_brainlink import BrainLinkEEGSource
from src.input.eeg.eeg_source_simulated import SimulatedEEGSource
from src.input.eeg.recorder import EEGRecorder
from src.input.eeg.mne_pipeline import MNEPipeline
from src.input.eeg.features import FeatureExtractor
from src.input.eeg.decoder import EEGDecoder
from src.input.eeg.circuit_breaker import EEGCircuitBreaker

__all__ = ['EEGSample', 'EEGSource', 'EEGWindow', 'EEGFeatures', 'EEGRingBuffer', 'ReplayDevice', 'BrainLinkDevice', 'BrainLinkEEGSource', 'SimulatedEEGSource', 'EEGRecorder', 'MNEPipeline', 'FeatureExtractor', 'EEGDecoder', 'EEGCircuitBreaker', 'EEGDecisionSource']
