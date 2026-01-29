"""Tests for CameraStream module."""

import unittest
import numpy as np
from vision.camera_stream import CameraStream, CameraConfig, CameraFrame


class TestCameraStream(unittest.TestCase):
    """Test CameraStream functionality."""
    
    def test_mock_mode_initialization(self):
        """Test that mock mode initializes correctly."""
        config = CameraConfig(mock_mode=True, width=320, height=240)
        stream = CameraStream(config, seed=42)
        
        self.assertFalse(stream.is_running)
        self.assertEqual(stream.frame_id, 0)
    
    def test_mock_mode_start(self):
        """Test starting mock mode."""
        config = CameraConfig(mock_mode=True)
        stream = CameraStream(config, seed=42)
        
        result = stream.start()
        self.assertTrue(result)
        self.assertTrue(stream.is_running)
        self.assertTrue(stream.is_alive())
    
    def test_mock_mode_get_frame(self):
        """Test getting frames from mock mode."""
        config = CameraConfig(mock_mode=True, width=320, height=240, target_fps=30)
        stream = CameraStream(config, seed=42)
        stream.start()
        
        frame = stream.get_frame()
        self.assertIsNotNone(frame)
        self.assertIsInstance(frame, CameraFrame)
        self.assertEqual(frame.frame_id, 0)
        self.assertEqual(frame.width, 320)
        self.assertEqual(frame.height, 240)
        self.assertEqual(frame.image.shape, (240, 320, 3))
        
        # Get another frame
        frame2 = stream.get_frame()
        self.assertIsNotNone(frame2)
        self.assertEqual(frame2.frame_id, 1)
        self.assertNotEqual(frame.timestamp, frame2.timestamp)
    
    def test_mock_mode_deterministic(self):
        """Test that mock mode is deterministic with same seed."""
        config = CameraConfig(mock_mode=True, width=100, height=100)
        
        # First run
        stream1 = CameraStream(config, seed=42)
        stream1.start()
        frame1 = stream1.get_frame()
        stream1.stop()
        
        # Second run with same seed
        stream2 = CameraStream(config, seed=42)
        stream2.start()
        frame2 = stream2.get_frame()
        stream2.stop()
        
        # Should produce identical frames
        self.assertTrue(np.array_equal(frame1.image, frame2.image))
        self.assertEqual(frame1.frame_id, frame2.frame_id)
    
    def test_stop(self):
        """Test stopping the stream."""
        config = CameraConfig(mock_mode=True)
        stream = CameraStream(config)
        stream.start()
        
        self.assertTrue(stream.is_running)
        stream.stop()
        self.assertFalse(stream.is_running)
        self.assertFalse(stream.is_alive())
    
    def test_get_frame_when_stopped(self):
        """Test that get_frame returns None when stopped."""
        config = CameraConfig(mock_mode=True)
        stream = CameraStream(config)
        
        # Not started
        frame = stream.get_frame()
        self.assertIsNone(frame)
        
        # Started then stopped
        stream.start()
        stream.stop()
        frame = stream.get_frame()
        self.assertIsNone(frame)
    
    def test_context_manager(self):
        """Test using CameraStream as context manager."""
        config = CameraConfig(mock_mode=True)
        
        with CameraStream(config) as stream:
            self.assertTrue(stream.is_running)
            frame = stream.get_frame()
            self.assertIsNotNone(frame)
        
        # Should be stopped after context exit
        self.assertFalse(stream.is_running)
    
    def test_frame_metadata(self):
        """Test that frames have correct metadata."""
        config = CameraConfig(mock_mode=True, width=640, height=480, target_fps=30)
        stream = CameraStream(config, seed=42)
        stream.start()
        
        frame = stream.get_frame()
        self.assertIsNotNone(frame)
        self.assertGreater(frame.timestamp, 0)
        self.assertGreater(frame.fps, 0)
        self.assertEqual(frame.width, 640)
        self.assertEqual(frame.height, 480)
        self.assertEqual(frame.image.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()

