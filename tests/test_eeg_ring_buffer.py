"""Tests for EEG ring buffer"""
import pytest
import numpy as np
from src.input.eeg.ring_buffer import EEGRingBuffer
from src.input.eeg.types import EEGSample


def test_push_and_window():
    buf = EEGRingBuffer(capacity_sec=2.0, expected_sfreq=100)
    
    for i in range(200):
        buf.push(EEGSample(timestamp_ms=i * 10.0, value=float(i)))
    
    window = buf.get_window(1.0)
    assert window.is_valid
    assert len(window.data) == 100


def test_empty_buffer_returns_invalid():
    buf = EEGRingBuffer(capacity_sec=2.0, expected_sfreq=100)
    window = buf.get_window(1.0)
    assert not window.is_valid


def test_insufficient_data_returns_invalid():
    buf = EEGRingBuffer(capacity_sec=2.0, expected_sfreq=100)
    for i in range(10):
        buf.push(EEGSample(timestamp_ms=i * 10.0, value=float(i)))
    
    window = buf.get_window(1.0)
    assert not window.is_valid  # Only 10 samples, need ~100


def test_batch_push():
    buf = EEGRingBuffer(capacity_sec=2.0, expected_sfreq=100)
    
    values = np.arange(150, dtype=np.float64)
    timestamps = np.arange(150, dtype=np.float64) * 10.0
    buf.push_batch(values, timestamps)
    
    window = buf.get_window(1.0)
    assert window.is_valid
    assert len(window.data) == 100



