"""MQTT helpers for Zigbee2MQTT IR emitters."""

from __future__ import annotations

import json
from typing import Any

from .const import DEFAULT_BASE_TOPIC


def build_topic(
    friendly_name: str,
    command: str = "ir_code_to_send",
    base_topic: str = DEFAULT_BASE_TOPIC,
) -> str:
    """Build the Zigbee2MQTT set topic for an exposed command."""

    return f"{base_topic}/{friendly_name}/set/{command}"


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
        return json.dumps(raw_timings())

    return str(command)
