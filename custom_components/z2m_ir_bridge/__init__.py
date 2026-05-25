"""Zigbee2MQTT IR Bridge integration."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_BASE_TOPIC,
    CONF_DISCOVERY_PREFIX,
    CONF_ENABLE_AUTO,
    CONF_MANUAL_FRIENDLY_NAMES,
    DEFAULT_BASE_TOPIC,
    DEFAULT_DISCOVERY_PREFIX,
    DOMAIN,
    PLATFORMS,
    SIGNAL_NEW_IR_DEVICE,
)
from .device_registry import is_ir_device, normalize_device

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Z2M IR Bridge from a config entry."""

    base_topic = entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
    discovery_prefix = entry.data.get(CONF_DISCOVERY_PREFIX, DEFAULT_DISCOVERY_PREFIX)
    enable_auto = entry.data.get(CONF_ENABLE_AUTO, True)
    manual_friendly_names = _manual_names(entry.data.get(CONF_MANUAL_FRIENDLY_NAMES, ""))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "devices": {},
        "unsub": [],
    }

    @callback
    def maybe_add_device(device: dict[str, Any]) -> None:
        normalized = normalize_device(device)
        if normalized is None:
            return

        if not enable_auto and normalized["friendly_name"] not in manual_friendly_names:
            return

        if not is_ir_device(normalized, manual_friendly_names):
            return

        devices = hass.data[DOMAIN][entry.entry_id]["devices"]
        friendly_name = normalized["friendly_name"]
        is_new = friendly_name not in devices
        devices[friendly_name] = normalized

        if is_new:
            async_dispatcher_send(
                hass,
                SIGNAL_NEW_IR_DEVICE.format(entry.entry_id),
                normalized,
            )

    @callback
    def bridge_devices_message(message) -> None:
        try:
            payload = json.loads(message.payload)
        except (TypeError, ValueError):
            _LOGGER.debug("Ignoring non-JSON Zigbee2MQTT bridge payload")
            return

        if not isinstance(payload, list):
            return

        for device in payload:
            if isinstance(device, dict):
                maybe_add_device(device)

    @callback
    def discovery_message(message) -> None:
        try:
            payload = json.loads(message.payload)
        except (TypeError, ValueError):
            _LOGGER.debug("Ignoring non-JSON MQTT discovery payload")
            return

        if isinstance(payload, dict):
            maybe_add_device(payload)

    unsub_bridge = await mqtt.async_subscribe(
        hass,
        f"{base_topic}/bridge/devices",
        bridge_devices_message,
        0,
    )
    unsub_discovery = await mqtt.async_subscribe(
        hass,
        f"{discovery_prefix}/+/+/config",
        discovery_message,
        0,
    )
    unsub_discovery_with_node = await mqtt.async_subscribe(
        hass,
        f"{discovery_prefix}/+/+/+/config",
        discovery_message,
        0,
    )

    hass.data[DOMAIN][entry.entry_id]["unsub"].extend(
        [unsub_bridge, unsub_discovery, unsub_discovery_with_node]
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, {})

    for unsubscribe in data.get("unsub", []):
        unsubscribe()

    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)

    return unload_ok


def _manual_names(value: str | list[str] | tuple[str, ...]) -> set[str]:
    """Parse manual friendly names from config flow input."""

    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}

    return {str(item).strip() for item in value if str(item).strip()}
