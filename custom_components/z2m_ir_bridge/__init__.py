"""Zigbee2MQTT IR Bridge integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ATTR_CODE,
    ATTR_FRIENDLY_NAME,
    ATTR_REPEAT,
    CONF_BASE_TOPIC,
    CONF_DISCOVERY_PREFIX,
    CONF_ENABLE_AUTO,
    CONF_MANUAL_FRIENDLY_NAMES,
    DEFAULT_BASE_TOPIC,
    DEFAULT_DISCOVERY_PREFIX,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND_CODE,
    SIGNAL_NEW_IR_DEVICE,
)
from .device_registry import is_ir_device, normalize_device
from .mqtt import build_payload, build_topic

_LOGGER = logging.getLogger(__name__)

SEND_CODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CODE): cv.string,
        vol.Optional(ATTR_FRIENDLY_NAME): cv.string,
        vol.Optional(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_REPEAT, default=1): vol.Coerce(int),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Z2M IR Bridge from a config entry."""

    base_topic = entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
    discovery_prefix = entry.data.get(CONF_DISCOVERY_PREFIX, DEFAULT_DISCOVERY_PREFIX)
    enable_auto = entry.data.get(CONF_ENABLE_AUTO, True)
    manual_friendly_names = _manual_names(entry.data.get(CONF_MANUAL_FRIENDLY_NAMES, ""))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "base_topic": base_topic,
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

    _async_register_services(hass)

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


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""

    if hass.services.has_service(DOMAIN, SERVICE_SEND_CODE):
        return

    async def async_send_code(call) -> None:
        code = call.data[ATTR_CODE]
        repeat = max(1, call.data[ATTR_REPEAT])
        friendly_name = call.data.get(ATTR_FRIENDLY_NAME)

        if friendly_name is None and (entity_id := call.data.get(CONF_ENTITY_ID)):
            friendly_name = _friendly_name_from_entity_id(hass, entity_id)

        if friendly_name is None:
            raise HomeAssistantError("friendly_name or entity_id is required")

        base_topic = _base_topic_for_device(hass, friendly_name)
        topic = build_topic(friendly_name, base_topic=base_topic)
        payload = build_payload(code)

        for _ in range(repeat):
            await hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": topic,
                    "payload": payload,
                },
                blocking=True,
            )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_CODE,
        async_send_code,
        schema=SEND_CODE_SCHEMA,
    )


def _base_topic_for_device(hass: HomeAssistant, friendly_name: str) -> str:
    """Return the base topic for a known device."""

    for data in hass.data.get(DOMAIN, {}).values():
        if friendly_name in data.get("devices", {}):
            return data.get("base_topic", DEFAULT_BASE_TOPIC)

    for data in hass.data.get(DOMAIN, {}).values():
        return data.get("base_topic", DEFAULT_BASE_TOPIC)

    return DEFAULT_BASE_TOPIC


def _friendly_name_from_entity_id(hass: HomeAssistant, entity_id: str) -> str | None:
    """Resolve an integration entity id to a Zigbee2MQTT friendly name."""

    entity_state = hass.states.get(entity_id)
    entity_name = entity_state.name if entity_state is not None else None

    for data in hass.data.get(DOMAIN, {}).values():
        for friendly_name in data.get("devices", {}):
            if entity_id.endswith(friendly_name.lower().replace(" ", "_")):
                return friendly_name
            if entity_name in {friendly_name, f"{friendly_name} IR emitter"}:
                return friendly_name

    return None


def _manual_names(value: str | list[str] | tuple[str, ...]) -> set[str]:
    """Parse manual friendly names from config flow input."""

    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}

    return {str(item).strip() for item in value if str(item).strip()}
