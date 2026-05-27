"""Zigbee2MQTT IR Bridge integration."""

from __future__ import annotations

import json
import logging
from importlib.util import find_spec
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
    ATTR_BACKEND,
    ATTR_CODE,
    ATTR_FRIENDLY_NAME,
    ATTR_REPEAT,
    ATTR_ZHA_CLUSTER_ID,
    ATTR_ZHA_COMMAND,
    ATTR_ZHA_ENDPOINT_ID,
    ATTR_ZHA_IEEE,
    BACKEND_Z2M,
    BACKEND_ZHA,
    CONF_BASE_TOPIC,
    CONF_DISCOVERY_PREFIX,
    CONF_ENABLE_AUTO,
    CONF_ENABLE_Z2M,
    CONF_MANUAL_FRIENDLY_NAMES,
    CONF_ZHA_DEVICES,
    DEFAULT_BASE_TOPIC,
    DEFAULT_DISCOVERY_PREFIX,
    DEFAULT_ZHA_CLUSTER_ID,
    DEFAULT_ZHA_COMMAND,
    DEFAULT_ZHA_ENDPOINT_ID,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND_CODE,
    SIGNAL_NEW_IR_DEVICE,
)
from .device_registry import is_ir_device, normalize_device
from .mqtt_helpers import build_payload, build_topic, command_to_z2m_code

_LOGGER = logging.getLogger(__name__)

SEND_CODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CODE): cv.string,
        vol.Optional(ATTR_BACKEND): vol.In([BACKEND_Z2M, BACKEND_ZHA]),
        vol.Optional(ATTR_FRIENDLY_NAME): cv.string,
        vol.Optional(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_REPEAT, default=1): vol.Coerce(int),
        vol.Optional(ATTR_ZHA_CLUSTER_ID, default=DEFAULT_ZHA_CLUSTER_ID): vol.Coerce(int),
        vol.Optional(ATTR_ZHA_COMMAND, default=DEFAULT_ZHA_COMMAND): vol.Coerce(int),
        vol.Optional(ATTR_ZHA_ENDPOINT_ID, default=DEFAULT_ZHA_ENDPOINT_ID): vol.Coerce(int),
        vol.Optional(ATTR_ZHA_IEEE): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Z2M IR Bridge from a config entry."""

    entry_config = {**entry.data, **entry.options}
    base_topic = entry_config.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC)
    discovery_prefix = entry_config.get(CONF_DISCOVERY_PREFIX, DEFAULT_DISCOVERY_PREFIX)
    enable_auto = entry_config.get(CONF_ENABLE_AUTO, True)
    enable_z2m = entry_config.get(CONF_ENABLE_Z2M, True)
    manual_friendly_names = _manual_names(
        entry_config.get(CONF_MANUAL_FRIENDLY_NAMES, "")
    )
    manual_zha_devices = _zha_devices(entry_config.get(CONF_ZHA_DEVICES, ""))

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "base_topic": base_topic,
        "devices": {},
        "unsub": [],
    }
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    hass.data[DOMAIN][entry.entry_id]["devices"].update(manual_zha_devices)

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
        normalized.setdefault(ATTR_BACKEND, BACKEND_Z2M)
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

    if enable_z2m:
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

    if _infrared_platform_available():
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    else:
        _LOGGER.warning(
            "Home Assistant infrared platform is not available; IR entities will "
            "not be created, but the %s.%s service remains available",
            DOMAIN,
            SERVICE_SEND_CODE,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = True
    if _infrared_platform_available():
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, {})

    for unsubscribe in data.get("unsub", []):
        unsubscribe()

    if not hass.data.get(DOMAIN):
        hass.data.pop(DOMAIN, None)

    return unload_ok


def _infrared_platform_available() -> bool:
    """Return whether this Home Assistant build includes the infrared platform."""

    return find_spec("homeassistant.components.infrared") is not None


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry after options change."""

    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""

    if hass.services.has_service(DOMAIN, SERVICE_SEND_CODE):
        return

    async def async_send_code(call) -> None:
        code = call.data[ATTR_CODE]
        repeat = max(1, call.data[ATTR_REPEAT])
        backend = call.data.get(ATTR_BACKEND)
        friendly_name = call.data.get(ATTR_FRIENDLY_NAME)
        device = None

        if friendly_name is None and (entity_id := call.data.get(CONF_ENTITY_ID)):
            friendly_name = _friendly_name_from_entity_id(hass, entity_id)

        if friendly_name is not None:
            device = _device_for_friendly_name(hass, friendly_name)

        if backend is None and call.data.get(ATTR_ZHA_IEEE):
            backend = BACKEND_ZHA
        if backend is None and device is not None:
            backend = device.get(ATTR_BACKEND, BACKEND_Z2M)
        if backend is None:
            backend = BACKEND_Z2M

        if backend == BACKEND_ZHA:
            await _async_send_zha_code(hass, call.data, device, code, repeat)
            return

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


async def _async_send_zha_code(
    hass: HomeAssistant,
    data: dict[str, Any],
    device: dict[str, Any] | None,
    code: Any,
    repeat: int,
) -> None:
    """Send a raw learned IR code through ZHA."""

    zha_ieee = data.get(ATTR_ZHA_IEEE) or (device or {}).get(ATTR_ZHA_IEEE)
    if not zha_ieee:
        raise HomeAssistantError("zha_ieee is required for ZHA IR sending")

    endpoint_id = data.get(ATTR_ZHA_ENDPOINT_ID) or (device or {}).get(
        ATTR_ZHA_ENDPOINT_ID,
        DEFAULT_ZHA_ENDPOINT_ID,
    )
    cluster_id = data.get(ATTR_ZHA_CLUSTER_ID) or (device or {}).get(
        ATTR_ZHA_CLUSTER_ID,
        DEFAULT_ZHA_CLUSTER_ID,
    )
    command = data.get(ATTR_ZHA_COMMAND) or (device or {}).get(
        ATTR_ZHA_COMMAND,
        DEFAULT_ZHA_COMMAND,
    )

    service_data = {
        "cluster_type": "in",
        "ieee": zha_ieee,
        "endpoint_id": int(endpoint_id),
        "command": int(command),
        "params": {"code": command_to_z2m_code(code)},
        "command_type": "server",
        "cluster_id": int(cluster_id),
    }

    _LOGGER.debug(
        "Sending ZHA IR command to %s endpoint %s cluster %s command %s",
        zha_ieee,
        endpoint_id,
        cluster_id,
        command,
    )

    for _ in range(repeat):
        await hass.services.async_call(
            "zha",
            "issue_zigbee_cluster_command",
            service_data,
            blocking=True,
        )


def _device_for_friendly_name(
    hass: HomeAssistant,
    friendly_name: str,
) -> dict[str, Any] | None:
    """Return the stored device metadata for a friendly name."""

    for data in hass.data.get(DOMAIN, {}).values():
        device = data.get("devices", {}).get(friendly_name)
        if device is not None:
            return device

    return None


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


def _zha_devices(value: str) -> dict[str, dict[str, Any]]:
    """Parse manual ZHA devices from config flow input."""

    devices = {}
    for line in value.splitlines():
        if not (line := line.strip()):
            continue

        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2:
            continue

        friendly_name = parts[0]
        try:
            devices[friendly_name] = {
                ATTR_BACKEND: BACKEND_ZHA,
                ATTR_FRIENDLY_NAME: friendly_name,
                ATTR_ZHA_IEEE: parts[1],
                ATTR_ZHA_ENDPOINT_ID: _int_part(parts, 2, DEFAULT_ZHA_ENDPOINT_ID),
                ATTR_ZHA_CLUSTER_ID: _int_part(parts, 3, DEFAULT_ZHA_CLUSTER_ID),
                ATTR_ZHA_COMMAND: _int_part(parts, 4, DEFAULT_ZHA_COMMAND),
                "model": "ZHA Tuya IR",
            }
        except ValueError:
            _LOGGER.warning("Ignoring invalid ZHA IR device line: %s", line)

    return devices


def _int_part(parts: list[str], index: int, default: int) -> int:
    """Return a parsed integer from a split config line."""

    if len(parts) <= index or not parts[index]:
        return default

    return int(parts[index])
