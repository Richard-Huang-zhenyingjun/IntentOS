"""
BrainLink client - serial communication with BrainLink Lite.
Week 7: ThinkGear/TGAM packet protocol parser.
"""

from dataclasses import dataclass
from typing import Optional, List
import time
import serial
import serial.tools.list_ports


@dataclass
class BrainLinkSample:
    """
    Raw sample from BrainLink device.
    
    Attributes:
        timestamp: Unix timestamp of sample
        attention: Attention metric (0-100), or None if not available
        meditation: Meditation metric (0-100), or None if not available
        signal_quality: Signal quality (0=good, 200=no contact), or None
        raw_eeg: Raw EEG values (optional)
        source: Data source identifier
    """
    timestamp: float
    attention: Optional[int] = None
    meditation: Optional[int] = None
    signal_quality: Optional[int] = None
    raw_eeg: Optional[List[int]] = None
    source: str = "brainlink"
    
    def is_valid(self) -> bool:
        """Check if sample has required metrics."""
        return self.attention is not None


class BrainLinkClient:
    """
    Serial client for BrainLink Lite device.
    
    Implements ThinkGear/TGAM protocol:
    - Packet format: [SYNC][SYNC][PLENGTH][PAYLOAD][CHECKSUM]
    - Extracts attention, meditation, signal quality
    
    Week 7: Serial transport only (Bluetooth in future).
    """
    
    def __init__(self, cfg: dict):
        """
        Initialize BrainLink client.
        
        Args:
            cfg: Configuration dict (eeg.brainlink section)
        """
        self.cfg = cfg
        self.serial_port: Optional[serial.Serial] = None
        self.port_name: Optional[str] = None
        self.connected = False
        
        # Packet parsing state
        self.buffer = bytearray()
        self.last_packet_time = 0.0
        
        # Config shortcuts
        bl_cfg = cfg['eeg']['brainlink']
        self.baudrate = bl_cfg['baudrate']
        self.read_timeout = bl_cfg['read_timeout']
        self.packet_timeout = bl_cfg['packet_timeout']
    
    def start(self) -> bool:
        """
        Connect to BrainLink device.
        
        Returns:
            True if connection successful
        """
        port = self.cfg['eeg']['brainlink']['serial_port']
        
        # Auto-scan if port not specified
        if not port:
            port = self._find_brainlink_port()
            if not port:
                print("⚠️  No BrainLink device found")
                return False
        
        try:
            self.serial_port = serial.Serial(
                port,
                baudrate=self.baudrate,
                timeout=self.read_timeout
            )
            self.port_name = port
            self.connected = True
            self.last_packet_time = time.time()
            
            print(f"✓ BrainLink connected: {port} @ {self.baudrate} baud")
            return True
            
        except Exception as e:
            print(f"⚠️  BrainLink connection failed: {e}")
            return False
    
    def _find_brainlink_port(self) -> Optional[str]:
        """Auto-detect BrainLink serial port."""
        ports = serial.tools.list_ports.comports()
        
        # Look for common BrainLink patterns
        patterns = ['brainlink', 'thinggear', 'neurosky', 'usb']
        
        for port in ports:
            port_str = str(port).lower()
            if any(pattern in port_str for pattern in patterns):
                print(f"  Found candidate: {port.device}")
                return port.device
        
        # Fallback: try first available port
        if ports:
            print(f"  Using first available port: {ports[0].device}")
            return ports[0].device
        
        return None
    
    def read_sample(self) -> Optional[BrainLinkSample]:
        """
        Read next sample from BrainLink.
        
        Returns:
            BrainLinkSample if valid packet received, else None
        """
        if not self.connected or self.serial_port is None:
            return None
        
        try:
            # Read available data
            if self.serial_port.in_waiting > 0:
                data = self.serial_port.read(self.serial_port.in_waiting)
                self.buffer.extend(data)
            
            # Try to parse packet
            packet = self._parse_packet()
            
            if packet:
                self.last_packet_time = time.time()
                return packet
            
            # Check for timeout
            if time.time() - self.last_packet_time > self.packet_timeout:
                print("⚠️  BrainLink packet timeout")
                return BrainLinkSample(
                    timestamp=time.time(),
                    signal_quality=200  # No contact
                )
            
            return None
            
        except Exception as e:
            print(f"⚠️  BrainLink read error: {e}")
            return None
    
    def _parse_packet(self) -> Optional[BrainLinkSample]:
        """
        Parse ThinkGear packet from buffer.
        
        Packet format:
        [0xAA][0xAA][PLENGTH][PAYLOAD...][CHECKSUM]
        
        Returns:
            BrainLinkSample if valid packet found
        """
        # Need at least sync bytes + length
        if len(self.buffer) < 4:
            return None
        
        # Look for sync pattern (0xAA 0xAA)
        sync_idx = -1
        for i in range(len(self.buffer) - 1):
            if self.buffer[i] == 0xAA and self.buffer[i+1] == 0xAA:
                sync_idx = i
                break
        
        if sync_idx == -1:
            # No sync found - clear old data
            if len(self.buffer) > 100:
                self.buffer.clear()
            return None
        
        # Remove data before sync
        if sync_idx > 0:
            self.buffer = self.buffer[sync_idx:]
        
        # Check if full packet available
        if len(self.buffer) < 4:
            return None
        
        plength = self.buffer[2]
        packet_size = 4 + plength  # sync(2) + length(1) + payload + checksum(1)
        
        if len(self.buffer) < packet_size:
            return None  # Wait for more data
        
        # Extract packet
        payload = self.buffer[3:3+plength]
        checksum = self.buffer[3+plength]
        
        # Verify checksum
        calc_checksum = (~sum(payload)) & 0xFF
        if checksum != calc_checksum:
            print(f"⚠️  Checksum mismatch: {checksum} != {calc_checksum}")
            self.buffer = self.buffer[packet_size:]
            return None
        
        # Parse payload
        sample = self._parse_payload(payload)
        
        # Remove parsed packet from buffer
        self.buffer = self.buffer[packet_size:]
        
        return sample
    
    def _parse_payload(self, payload: bytearray) -> BrainLinkSample:
        """Parse payload bytes into sample."""
        sample = BrainLinkSample(timestamp=time.time())
        
        i = 0
        while i < len(payload):
            code = payload[i]
            
            # Extended code byte
            if code == 0x55:
                i += 1
                continue
            
            # Single-byte values
            if code == 0x02:  # Signal quality
                sample.signal_quality = payload[i+1]
                i += 2
            elif code == 0x04:  # Attention
                sample.attention = payload[i+1]
                i += 2
            elif code == 0x05:  # Meditation
                sample.meditation = payload[i+1]
                i += 2
            # Multi-byte values
            elif code >= 0x80:  # Has length byte
                length = payload[i+1]
                # Skip for now (raw EEG data)
                i += 2 + length
            else:
                i += 1
        
        return sample
    
    def close(self) -> None:
        """Close serial connection."""
        if self.serial_port is not None:
            self.serial_port.close()
            self.connected = False
            print(f"✓ BrainLink disconnected: {self.port_name}")
    
    def get_status(self) -> dict:
        """Get connection status."""
        return {
            "connected": self.connected,
            "port": self.port_name,
            "last_packet_age": time.time() - self.last_packet_time if self.connected else None,
        }




