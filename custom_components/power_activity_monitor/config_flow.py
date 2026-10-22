"""UI configuration for the power activity monitor."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TimeSelector,
)

from .const import CONF_NOTIFY_ENTITY, CONF_REPORT_TIME, DEFAULT_REPORT_TIME, DOMAIN


def _schema(values: dict) -> vol.Schema:
    notify_key = (
        vol.Optional(CONF_NOTIFY_ENTITY, default=values[CONF_NOTIFY_ENTITY])
        if values.get(CONF_NOTIFY_ENTITY)
        else vol.Optional(CONF_NOTIFY_ENTITY)
    )
    return vol.Schema(
        {
            notify_key: EntitySelector(EntitySelectorConfig(domain="notify")),
            vol.Required(
                CONF_REPORT_TIME,
                default=values.get(CONF_REPORT_TIME, DEFAULT_REPORT_TIME),
            ): TimeSelector(),
        }
    )


class PowerActivityMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the single local monitor."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        await self.async_set_unique_id("host_power_activity")
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Монитор электропитания", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PowerActivityMonitorOptionsFlow()


class PowerActivityMonitorOptionsFlow(config_entries.OptionsFlow):
    """Change notification destination and weekly report time."""

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            user_input[CONF_NOTIFY_ENTITY] = user_input.get(CONF_NOTIFY_ENTITY, "")
            return self.async_create_entry(title="", data=user_input)
        values = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(values))
