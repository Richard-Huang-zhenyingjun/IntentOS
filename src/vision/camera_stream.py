"""Camera Input Stream - Live camera feed with graceful failure handling."""

import cv2
import numpy as np
import time
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class CameraFrame:
    """Single camera frame with metadata."""
    frame_id: int
    timestamp: float
    image: np.ndarray  # BGR format
    width: int
    height: int
    fps: float


@dataclass
class CameraConfig:
    """Camera configuration."""
    device_index: int = 0
    target_fps: int = 30
    width: int = 640
    height: int = 480
    auto_exposure: bool = True
    mock_mode: bool = False  # For deterministic testing


class CameraStream:
    """
    Camera input stream with graceful failure handling.
    
    Key properties:
    - Non-blocking (get_frame() returns None if no frame available)
    - Graceful degradation (system continues if camera fails)
    - Deterministic mock mode for testing
    - Never mutates core state (read-only pipeline)
    """
    
    def __init__(self, config: CameraConfig, seed: int = 42):
        """
        Initialize camera stream.
        
        Args:
            config: Camera configuration
            seed: Random seed for mock mode (deterministic testing)
        """
        self.config = config
        self.seed = seed
        self.cap = None
        self.frame_id = 0
        self.last_frame_time = 0.0
        self.actual_fps = config.target_fps
        self.is_running = False
        
        # Mock mode setup
        if config.mock_mode:
            np.random.seed(seed)
            logger.info(f"CameraStream: Mock mode enabled (seed={seed})")
    
    def start(self) -> bool:
        """
        Start camera stream.
        
        Returns:
            True if camera started successfully, False otherwise
        """
        if self.config.mock_mode:
            self.is_running = True
            logger.info("CameraStream: Mock mode started")
            return True
        
        try:
            self.cap = cv2.VideoCapture(self.config.device_index)
            
            if not self.cap.isOpened():
                logger.warning(f"CameraStream: Failed to open camera {self.config.device_index}")
                return False
            
            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.config.target_fps)
            
            if not self.config.auto_exposure:
                self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0)
            
            # Test read to verify camera works
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.warning("CameraStream: Camera opened but cannot read frames")
                self.cap.release()
                self.cap = None
                return False
            
            self.is_running = True
            self.last_frame_time = time.time()
            logger.info(f"CameraStream: Started successfully (device={self.config.device_index}, "
                       f"resolution={self.config.width}x{self.config.height}, "
                       f"fps={self.config.target_fps})")
            return True
            
        except Exception as e:
            logger.error(f"CameraStream: Exception during start: {e}")
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            return False
    
    def get_frame(self) -> Optional[CameraFrame]:
        """
        Get next camera frame (non-blocking).
        
        Returns:
            CameraFrame if available, None otherwise (non-blocking)
        """
        if not self.is_running:
            return None
        
        # Mock mode: generate synthetic frames
        if self.config.mock_mode:
            return self._get_mock_frame()
        
        # Real camera mode
        if self.cap is None or not self.cap.isOpened():
            return None
        
        try:
            ret, frame = self.cap.read()
            
            if not ret or frame is None:
                # Camera may have disconnected
                logger.warning("CameraStream: Failed to read frame (camera may have disconnected)")
                return None
            
            # Resize to target resolution if needed
            if frame.shape[1] != self.config.width or frame.shape[0] != self.config.height:
                frame = cv2.resize(frame, (self.config.width, self.config.height))
            
            # Calculate FPS
            current_time = time.time()
            if self.last_frame_time > 0:
                dt = current_time - self.last_frame_time
                if dt > 0:
                    self.actual_fps = 0.9 * self.actual_fps + 0.1 * (1.0 / dt)
            self.last_frame_time = current_time
            
            # Create frame object
            camera_frame = CameraFrame(
                frame_id=self.frame_id,
                timestamp=current_time,
                image=frame.copy(),  # Copy to avoid reference issues
                width=self.config.width,
                height=self.config.height,
                fps=self.actual_fps
            )
            
            self.frame_id += 1
            return camera_frame
            
        except Exception as e:
            logger.error(f"CameraStream: Exception reading frame: {e}")
            return None
    
    def _get_mock_frame(self) -> Optional[CameraFrame]:
        """Generate synthetic frame for deterministic testing."""
        current_time = time.time()
        
        # Calculate FPS
        if self.last_frame_time > 0:
            dt = current_time - self.last_frame_time
            if dt > 0:
                self.actual_fps = 0.9 * self.actual_fps + 0.1 * (1.0 / dt)
        else:
            self.actual_fps = self.config.target_fps
        
        self.last_frame_time = current_time
        
        # Generate synthetic image (deterministic based on frame_id)
        np.random.seed(self.seed + self.frame_id)
        image = np.random.randint(0, 255, (self.config.height, self.config.width, 3), dtype=np.uint8)
        
        # Add some structure for testing (colored rectangle that moves)
        color = (int((self.frame_id * 17) % 255), 
                 int((self.frame_id * 23) % 255), 
                 int((self.frame_id * 31) % 255))
        x = (self.frame_id * 5) % (self.config.width - 100)
        y = (self.frame_id * 3) % (self.config.height - 100)
        cv2.rectangle(image, (x, y), (x + 100, y + 100), color, -1)
        
        camera_frame = CameraFrame(
            frame_id=self.frame_id,
            timestamp=current_time,
            image=image,
            width=self.config.width,
            height=self.config.height,
            fps=self.actual_fps
        )
        
        self.frame_id += 1
        return camera_frame
    
    def stop(self):
        """Stop camera stream and release resources."""
        self.is_running = False
        
        if self.cap is not None:
            try:
                self.cap.release()
                logger.info("CameraStream: Stopped and released")
            except Exception as e:
                logger.error(f"CameraStream: Error releasing camera: {e}")
            finally:
                self.cap = None
    
    def is_alive(self) -> bool:
        """
        Check if camera is still functioning.
        
        Returns:
            True if camera is operational, False otherwise
        """
        if not self.is_running:
            return False
        
        if self.config.mock_mode:
            return True
        
        if self.cap is None:
            return False
        
        try:
            return self.cap.isOpened()
        except Exception:
            return False
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

