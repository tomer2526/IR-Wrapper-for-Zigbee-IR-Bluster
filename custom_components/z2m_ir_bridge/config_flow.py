"""Config flow for Z2M IR Bridge."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import (
    CONF_BASE_TOPIC,
    CONF_DISCOVERY_PREFIX,
    CONF_ENABLE_AUTO,
    CONF_MANUAL_FRIENDLY_NAMES,
    DEFAULT_BASE_TOPIC,
    DEFAULT_DISCOVERY_PREFIX,
    DOMAIN,
)


class Z2MIRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Z2M IR Bridge."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Create the integration entry."""

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Z2M IR Bridge",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ENABLE_AUTO, default=True): bool,
                    vol.Optional(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC): str,
                    vol.Optional(
                        CONF_DISCOVERY_PREFIX,
                        default=DEFAULT_DISCOVERY_PREFIX,
                    ): str,
                    vol.Optional(
                        CONF_MANUAL_FRIENDLY_NAMES,
                        default="",
                    ): str,
                }
            ),
        )
