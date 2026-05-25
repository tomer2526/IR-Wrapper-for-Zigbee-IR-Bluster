"""Constants for the Z2M IR Bridge integration."""

from __future__ import annotations

DOMAIN = "z2m_ir_bridge"

DEFAULT_BASE_TOPIC = "zigbee2mqtt"
DEFAULT_DISCOVERY_PREFIX = "homeassistant"

PLATFORMS = ["infrared"]

CONF_BASE_TOPIC = "base_topic"
CONF_DISCOVERY_PREFIX = "discovery_prefix"
CONF_ENABLE_AUTO = "enable_auto"
CONF_MANUAL_FRIENDLY_NAMES = "manual_friendly_names"

ATTR_CODE = "code"
ATTR_FRIENDLY_NAME = "friendly_name"
ATTR_REPEAT = "repeat"

SERVICE_SEND_CODE = "send_code"

SIGNAL_NEW_IR_DEVICE = "z2m_ir_bridge_new_ir_device_{}"

IR_MODELS = {
    "ZS06",
    "TS120F",
    "TUYA_IR_BLASTER",
}

IR_KEYS = {
    "ir_code_to_send",
    "learn_ir_code",
    "learned_ir_code",
}
