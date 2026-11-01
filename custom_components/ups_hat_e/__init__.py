from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_I2C_BUS, DOMAIN
from .coordinator import UpsHatCoordinator
from .power_protection import PowerProtectionManager

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = UpsHatCoordinator(hass, entry.data[CONF_I2C_BUS])
    await coordinator.async_config_entry_first_refresh()
    manager = PowerProtectionManager(hass, entry, coordinator)
    manager.async_start()
    entry.async_on_unload(manager.async_stop)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.data[DOMAIN].pop(entry.entry_id)
    return True
