"""
BrainLink Lite BLE device driver.

Connects via serial/BLE and streams raw EEG samples.
Handles connection, reconnection, and packet parsing.

If BrainLink SDK isn't available, this module gracefully reports unavailable.
"""
import threading
import time
import logging
from typing import Callable, Optional
from src.input.eeg.device_base import EEGDeviceBase
from src.input.eeg.types import EEGSample

logger = logging.getLogger(__name__)

# Attempt to import BrainLink SDK
try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


class BrainLinkDevice(EEGDeviceBase):
    """
    BrainLink Lite real device driver.
    
    Connection: Serial over BLE (typically /dev/tty.BrainLink* on macOS)
    Protocol: BrainLink sends packets with raw EEG values.
    
    If serial is not available or device not found, reports unavailable
    and all reads return empty. Never crashes.
    """
    
    # BrainLink Lite packet markers (adjust to your device version)
    PACKET_HEADER = 0xAA
    PACKET_SYNC = 0xAA
    
    def __init__(self, config: dict):
        eeg_cfg = config.get('eeg', {})
        
        self.port = eeg_cfg.get('port', 'auto')
        self.baud_rate = eeg_cfg.get('baud_rate', 57600)
        self.expected_sfreq = eeg_cfg.get('expected_sfreq', 512)
        
        self._callback: Optional[Callable] = None
        self._serial: Optional['serial.Serial'] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        
        # Metrics
        self.total_packets = 0
        self.corrupt_packets = 0
        self.reconnect_count = 0
    
    def start(self):
        """Attempt to connect and begin streaming"""
        if not SERIAL_AVAILABLE:
            logger.warning("[BRAINLINK] pyserial not installed, device unavailable")
            return
        
        port = self._find_port() if self.port == 'auto' else self.port
        
        if port is None:
            logger.warning("[BRAINLINK] No device found")
            return
        
        try:
            self._serial = serial.Serial(port, self.baud_rate, timeout=1.0)
            self._connected = True
            self._running = True
            
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            
            logger.info(f"[BRAINLINK] Connected on {port} at {self.baud_rate} baud")
            
        except Exception as e:
            logger.error(f"[BRAINLINK] Connection failed: {e}")
            self._connected = False
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected and self._running
    
    def set_callback(self, callback: Callable[[EEGSample], None]):
        self._callback = callback
    
    def get_sfreq(self) -> float:
        return self.expected_sfreq
    
    def _find_port(self) -> Optional[str]:
        """Auto-detect BrainLink device port"""
        try:
            import serial.tools.list_ports
            ports = serial.tools.list_ports.comports()
            for port in ports:
                desc = (port.description or '').lower()
                name = (port.device or '').lower()
                if 'brainlink' in desc or 'brainlink' in name:
                    return port.device
                # Also check for common BLE serial names on macOS
                if 'tty.brain' in name or 'cu.brain' in name:
                    return port.device
        except Exception:
            pass
        return None
    
    def _read_loop(self):
        """Background thread: read and parse BrainLink packets"""
        session_start = time.time()
        
        while self._running:
            try:
                if not self._serial or not self._serial.is_open:
                    self._connected = False
                    time.sleep(1.0)
                    continue
                
                # Read one byte at a time looking for sync
                byte = self._serial.read(1)
                if not byte:
                    continue
                
                # Simple packet parsing (adjust to your BrainLink protocol)
                # BrainLink Lite typically sends: [0xAA, 0xAA, payload_len, ..., checksum]
                if byte[0] == self.PACKET_HEADER:
                    packet = self._read_packet()
                    if packet is not None:
                        self.total_packets += 1
                        
                        timestamp_ms = (time.time() - session_start) * 1000
                        
                        sample = EEGSample(
                            timestamp_ms=timestamp_ms,
                            value=packet['raw_value'],
                            channel=0,
                            valid=True,
                        )
                        
                        if self._callback:
                            self._callback(sample)
                    else:
                        self.corrupt_packets += 1
                        
            except serial.SerialException as e:
                logger.warning(f"[BRAINLINK] Serial error: {e}")
                self._connected = False
                time.sleep(1.0)
                # Attempt reconnect
                self._try_reconnect()
                
            except Exception as e:
                logger.error(f"[BRAINLINK] Unexpected error: {e}")
                time.sleep(0.1)
    
    def _read_packet(self) -> Optional[dict]:
        """
        Parse BrainLink packet.
        
        Adjust this to match your specific BrainLink Lite protocol version.
        Common format: [AA, AA, len, payload..., checksum]
        """
        try:
            # Read second sync byte
            sync2 = self._serial.read(1)
            if not sync2 or sync2[0] != self.PACKET_SYNC:
                return None
            
            # Read payload length
            plen_byte = self._serial.read(1)
            if not plen_byte:
                return None
            payload_len = plen_byte[0]
            
            if payload_len > 169 or payload_len < 1:
                return None
            
            # Read payload + checksum
            payload = self._serial.read(payload_len)
            checksum = self._serial.read(1)
            
            if len(payload) != payload_len or not checksum:
                return None
            
            # Verify checksum
            expected_checksum = sum(payload) & 0xFF
            expected_checksum = (~expected_checksum) & 0xFF
            
            if checksum[0] != expected_checksum:
                return None
            
            # Parse raw EEG value from payload
            # BrainLink Lite: raw value is typically in bytes at specific offsets
            # This parsing is protocol-version specific
            raw_value = self._parse_raw_eeg(payload)
            
            if raw_value is not None:
                return {'raw_value': raw_value}
            return None
            
        except Exception:
            return None
    
    def _parse_raw_eeg(self, payload: bytes) -> Optional[float]:
        """
        Extract raw EEG value from payload.
        
        BrainLink Lite raw EEG is typically a 16-bit signed value.
        Adjust byte offsets for your protocol version.
        """
        # Common BrainLink Lite format:
        # Payload byte 0 = signal quality (0=good, 200=off-head)
        # Payload bytes at EXCODE+offset = raw EEG (big-endian int16)
        
        # Simple approach: scan for raw EEG code (0x80) in payload
        i = 0
        while i < len(payload) - 2:
            if payload[i] == 0x80:  # Raw EEG code
                raw_len = payload[i + 1] if i + 1 < len(payload) else 0
                if raw_len == 2 and i + 3 < len(payload):
                    high = payload[i + 2]
                    low = payload[i + 3]
                    value = (high << 8) | low
                    if value >= 32768:
                        value -= 65536  # Convert to signed
                    return float(value)
            i += 1
        
        return None
    
    def _try_reconnect(self):
        """Attempt to reconnect to device"""
        self.reconnect_count += 1
        
        if self._serial and self._serial.is_open:
            self._serial.close()
        
        port = self._find_port() if self.port == 'auto' else self.port
        if port:
            try:
                self._serial = serial.Serial(port, self.baud_rate, timeout=1.0)
                self._connected = True
                logger.info(f"[BRAINLINK] Reconnected on {port}")
            except Exception:
                self._connected = False



