from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    CONF_CRITICAL_DELAY,
    CONF_CRITICAL_PERCENT,
    CONF_EMERGENCY_DELAY,
    CONF_EMERGENCY_PERCENT,
    CONF_I2C_BUS,
    CONF_NOTIFY_ON_BATTERY,
    CONF_SHUTDOWN_ENABLED,
    DEFAULT_I2C_BUS,
    DOMAIN,
    I2C_ADDRESS,
    OPTION_DEFAULTS,
)
from .i2c import InvalidDeviceError, read_device_identity

_LOGGER = logging.getLogger(__name__)


def _number(minimum: int, maximum: int, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return PowerProtectionOptionsFlow()

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            bus_number = int(user_input[CONF_I2C_BUS])
            try:
                await self.hass.async_add_executor_job(
                    read_device_identity, bus_number
                )
            except InvalidDeviceError:
                errors["base"] = "not_ups_hat"
            except OSError as err:
                _LOGGER.error(
                    "Unable to connect to UPS HAT on I2C bus %s: %s",
                    bus_number,
                    err,
                )
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{bus_number}-{I2C_ADDRESS:02x}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Waveshare UPS HAT (E)",
                    data={CONF_I2C_BUS: bus_number},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_I2C_BUS, default=DEFAULT_I2C_BUS): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=255,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )


class PowerProtectionOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_SHUTDOWN_ENABLED: user_input[CONF_SHUTDOWN_ENABLED],
                    CONF_NOTIFY_ON_BATTERY: user_input[CONF_NOTIFY_ON_BATTERY],
                    CONF_CRITICAL_PERCENT: int(user_input[CONF_CRITICAL_PERCENT]),
                    CONF_CRITICAL_DELAY: int(user_input[CONF_CRITICAL_DELAY]),
                    CONF_EMERGENCY_PERCENT: int(user_input[CONF_EMERGENCY_PERCENT]),
                    CONF_EMERGENCY_DELAY: int(user_input[CONF_EMERGENCY_DELAY]),
                },
            )

        current = {**OPTION_DEFAULTS, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SHUTDOWN_ENABLED, default=current[CONF_SHUTDOWN_ENABLED]
                ): BooleanSelector(),
                vol.Required(
                    CONF_CRITICAL_PERCENT, default=current[CONF_CRITICAL_PERCENT]
                ): _number(1, 100, "%"),
                vol.Required(
                    CONF_CRITICAL_DELAY, default=current[CONF_CRITICAL_DELAY]
                ): _number(0, 3600, "s"),
                vol.Required(
                    CONF_EMERGENCY_PERCENT, default=current[CONF_EMERGENCY_PERCENT]
                ): _number(1, 100, "%"),
                vol.Required(
                    CONF_EMERGENCY_DELAY, default=current[CONF_EMERGENCY_DELAY]
                ): _number(0, 3600, "s"),
                vol.Required(
                    CONF_NOTIFY_ON_BATTERY, default=current[CONF_NOTIFY_ON_BATTERY]
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

