"""Minimal, dependency-free MP4 inspection.

Just enough to validate a generated clip without pulling in ffmpeg: confirm the
file is an MP4 (has an `ftyp` box) and read its duration from the `mvhd` box.
"""

from __future__ import annotations

import struct


def is_mp4(data: bytes) -> bool:
    """True if the bytes look like an MP4/ISO-BMFF file (ftyp box near the start)."""
    return b"ftyp" in data[:64]


def parse_duration_seconds(data: bytes) -> float | None:
    """Read duration (seconds) from the mvhd box. Returns None if not found."""
    idx = data.find(b"mvhd")
    if idx == -1:
        return None
    # mvhd payload starts right after the 4-byte box type.
    p = idx + 4
    try:
        version = data[p]
        if version == 1:
            # version(1) flags(3) creation(8) modification(8) timescale(4) duration(8)
            timescale = struct.unpack(">I", data[p + 1 + 3 + 16 : p + 1 + 3 + 16 + 4])[0]
            duration = struct.unpack(">Q", data[p + 1 + 3 + 20 : p + 1 + 3 + 20 + 8])[0]
        else:
            # version(1) flags(3) creation(4) modification(4) timescale(4) duration(4)
            timescale = struct.unpack(">I", data[p + 1 + 3 + 8 : p + 1 + 3 + 8 + 4])[0]
            duration = struct.unpack(">I", data[p + 1 + 3 + 12 : p + 1 + 3 + 12 + 4])[0]
    except (struct.error, IndexError):
        return None
    if not timescale:
        return None
    return duration / timescale
