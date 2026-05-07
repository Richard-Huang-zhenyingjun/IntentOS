from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Iterable, Dict, Any

import serial


@dataclass
class EEGSample:
    t: float
    raw_eeg: Optional[int] = None
    attention: Optional[int] = None
    meditation: Optional[int] = None
    poor_signal: Optional[int] = None
    blink_strength: Optional[int] = None


class ThinkGearStream:
    """
    Live ThinkGear decoder from a serial port (/dev/tty.BrainLink_Lite).

    Reads bytes -> extracts packets -> decodes common codes -> yields EEGSample with timestamp.
    """

    def __init__(self, port: str = "/dev/tty.BrainLink_Lite", baud: int = 57600, timeout: float = 0.2):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.ser: Optional[serial.Serial] = None
        self._buf = bytearray()

    def connect(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def _read_into_buffer(self):
        if self.ser is None:
            return
        chunk = self.ser.read(1024)
        if chunk:
            self._buf.extend(chunk)

    def _pop_packet_payload(self) -> Optional[bytes]:
        """
        Return next valid ThinkGear payload from buffer if available, else None.
        Packet: AA AA PLEN [payload] CHK
        """
        b = self._buf
        n = len(b)
        if n < 5:
            return None

        # Find sync AA AA
        i = 0
        while i + 4 < n:
            if b[i] != 0xAA or b[i + 1] != 0xAA:
                i += 1
                continue

            plen = b[i + 2]
            if plen == 0 or plen > 170:
                i += 2
                continue

            end_payload = i + 3 + plen
            end_packet = end_payload + 1
            if end_packet > n:
                # not enough bytes yet
                break

            payload = bytes(b[i + 3 : end_payload])
            chk = b[end_payload]

            calc = 0xFF - (sum(payload) & 0xFF)
            if chk != calc:
                # bad checksum: shift by 1 to resync
                i += 1
                continue

            # consume up to end_packet
            del b[:end_packet]
            return payload

        # If we scanned far, drop leading junk to keep buffer bounded
        if i > 0:
            del b[:i]
        return None

    @staticmethod
    def _decode_payload(payload: bytes) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        i = 0
        L = len(payload)

        def read_u24(b0, b1, b2):
            return (b0 << 16) | (b1 << 8) | b2

        while i < L:
            code = payload[i]
            i += 1

            # Handle extended code prefix 0x55
            while code == 0x55 and i < L:
                code = payload[i]
                i += 1

            if i >= L:
                break

            # single-byte codes
            if code in (0x02, 0x04, 0x05, 0x16):
                val = payload[i]
                i += 1
                if code == 0x02:
                    out["poor_signal"] = val
                elif code == 0x04:
                    out["attention"] = val
                elif code == 0x05:
                    out["meditation"] = val
                elif code == 0x16:
                    out["blink_strength"] = val
                continue

            # variable-length codes
            vlen = payload[i]
            i += 1
            if i + vlen > L:
                break
            v = payload[i : i + vlen]
            i += vlen

            if code == 0x80 and vlen == 2:
                out["raw_eeg"] = int.from_bytes(v, "big", signed=True)
            elif code == 0x83 and vlen == 24:
                bands = [
                    "delta", "theta", "low_alpha", "high_alpha",
                    "low_beta", "high_beta", "low_gamma", "mid_gamma",
                ]
                vals = []
                for k in range(8):
                    vals.append(read_u24(v[3*k], v[3*k+1], v[3*k+2]))
                out["eeg_power"] = dict(zip(bands, vals))
            else:
                out.setdefault("unknown", []).append({"code": code, "len": vlen})

        return out

    def read_sample(self, max_wait_s: float = 0.5) -> Optional[EEGSample]:
        """
        Blocking-ish: wait up to max_wait_s for a valid packet, return decoded sample.
        """
        t_start = time.time()
        while time.time() - t_start < max_wait_s:
            self._read_into_buffer()
            payload = self._pop_packet_payload()
            if payload is None:
                continue

            rec = self._decode_payload(payload)
            return EEGSample(t=time.time(), **{k: rec.get(k) for k in [
                "raw_eeg", "attention", "meditation", "poor_signal", "blink_strength"
            ]})

        return None
