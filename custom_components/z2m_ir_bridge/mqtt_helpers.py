"""MQTT helpers for Zigbee2MQTT IR emitters."""

from __future__ import annotations

import base64
import json
import struct
from typing import Any

from .const import DEFAULT_BASE_TOPIC


def build_topic(
    friendly_name: str,
    command: str | None = None,
    base_topic: str = DEFAULT_BASE_TOPIC,
) -> str:
    """Build the Zigbee2MQTT set topic for device commands."""

    return f"{base_topic}/{friendly_name}/set"


def build_payload(code: Any) -> str:
    """Build a Zigbee2MQTT payload for the Tuya/Z2M IR send property."""

    return json.dumps({"ir_code_to_send": command_to_z2m_code(code)})


def command_to_z2m_code(command: Any) -> str:
    """Convert a Home Assistant infrared command or raw value to a Z2M code."""

    if isinstance(command, bytes):
        return command.decode()

    if isinstance(command, str):
        return command

    raw_timings = getattr(command, "get_raw_timings", None)
    if callable(raw_timings):
        return encode_tuya_ir(_flatten_raw_timings(raw_timings()))

    return str(command)


def encode_tuya_ir(timings: list[int]) -> str:
    """Encode raw IR timings to the Tuya base64 format used by ZS06."""

    payload = b"".join(
        struct.pack("<H", min(max(int(timing), 0), 65535)) for timing in timings
    )
    return base64.b64encode(_encode_fastlz_literal_blocks(payload)).decode("ascii")


def _flatten_raw_timings(raw_timings: Any) -> list[int]:
    """Flatten Home Assistant infrared timings to alternating positive durations."""

    timings: list[int] = []
    for timing in raw_timings:
        if isinstance(timing, int):
            timings.append(abs(timing))
            continue

        if isinstance(timing, (tuple, list)):
            timings.extend(abs(int(value)) for value in timing)
            continue

        high_us = getattr(timing, "high_us", None)
        low_us = getattr(timing, "low_us", None)
        if high_us is not None:
            timings.append(abs(int(high_us)))
        if low_us is not None:
            timings.append(abs(int(low_us)))

    return timings


def _encode_fastlz_literal_blocks(payload: bytes) -> bytes:
    """Encode a FastLZ-compatible stream using only literal blocks."""

    blocks = bytearray()
    for index in range(0, len(payload), 32):
        chunk = payload[index : index + 32]
        blocks.append(len(chunk) - 1)
        blocks.extend(chunk)
    return bytes(blocks)
