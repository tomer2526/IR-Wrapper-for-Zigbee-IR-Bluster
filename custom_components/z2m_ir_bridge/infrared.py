"""Infrared platform for Z2M IR Bridge."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC, DOMAIN, SIGNAL_NEW_IR_DEVICE
from .ir_entity import Z2MInfraredEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up discovered Zigbee2MQTT IR entities."""

    data = hass.data[DOMAIN][entry.entry_id]
    added: set[str] = set()

    @callback
    def add_device(device: dict) -> None:
        friendly_name = device["friendly_name"]
        if friendly_name in added:
            return

        added.add(friendly_name)
        async_add_entities(
            [
                Z2MInfraredEntity(
                    hass,
                    friendly_name,
                    entry.data.get(CONF_BASE_TOPIC, DEFAULT_BASE_TOPIC),
                    device,
                )
            ]
        )

    for device in data["devices"].values():
        add_device(device)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_NEW_IR_DEVICE.format(entry.entry_id),
            add_device,
        )
    )
