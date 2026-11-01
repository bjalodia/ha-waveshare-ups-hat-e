from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import UPDATE_INTERVAL_SECONDS
from .i2c import InvalidDeviceError, UpsSnapshot, read_snapshot

_LOGGER = logging.getLogger(__name__)


class UpsHatCoordinator(DataUpdateCoordinator[UpsSnapshot]):
    def __init__(self, hass: HomeAssistant, bus_number: int) -> None:
        self.bus_number = bus_number
        super().__init__(
            hass,
            _LOGGER,
            name="Waveshare UPS HAT (E)",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> UpsSnapshot:
        try:
            return await self.hass.async_add_executor_job(
                read_snapshot, self.bus_number
            )
        except (InvalidDeviceError, OSError) as err:
            raise UpdateFailed(f"Unable to read UPS HAT over I2C: {err}") from err
