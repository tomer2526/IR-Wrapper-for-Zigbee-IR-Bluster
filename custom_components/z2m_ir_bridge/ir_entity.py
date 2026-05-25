"""Infrared entity for Zigbee2MQTT IR emitters."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.infrared import InfraredEntity
from homeassistant.components.mqtt import DOMAIN as MQTT_DOMAIN
from homeassistant.core import HomeAssistant

from .const import DEFAULT_BASE_TOPIC, DOMAIN
from .mqtt_helpers import build_payload, build_topic

_LOGGER = logging.getLogger(__name__)


class Z2MInfraredEntity(InfraredEntity):
    """A Home Assistant infrared emitter backed by a Zigbee2MQTT IR device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        friendly_name: str,
        base_topic: str = DEFAULT_BASE_TOPIC,
        device: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the entity."""

        self.hass = hass
        self._friendly_name = friendly_name
        self._base_topic = base_topic
        self._device = device or {}

        self._attr_name = "IR emitter"
        self._attr_unique_id = f"{DOMAIN}_{friendly_name}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, friendly_name)},
            "name": friendly_name,
            "manufacturer": "Zigbee2MQTT",
            "model": self._device_model,
        }

    @property
    def _device_model(self) -> str | None:
        """Return the best available model value."""

        return (
            self._device.get("model_id")
            or self._device.get("model")
            or self._device.get("definition", {}).get("model")
            or self._device.get("device", {}).get("model")
            or self._device.get("dev", {}).get("mdl")
            or self._device.get("dev", {}).get("model")
        )

    async def async_send_command(self, command: Any, **kwargs: Any) -> None:
        """Send an IR command through Zigbee2MQTT."""

        repeat = int(kwargs.get("repeat", 1))
        topic = build_topic(
            self._friendly_name,
            base_topic=self._base_topic,
        )
        payload = build_payload(command)
        _LOGGER.debug(
            "Publishing IR command to %s from %s as %d payload bytes",
            topic,
            type(command).__name__,
            len(payload),
        )

        for _ in range(max(1, repeat)):
            await self.hass.services.async_call(
                MQTT_DOMAIN,
                "publish",
                {
                    "topic": topic,
                    "payload": payload,
                },
                blocking=True,
            )
