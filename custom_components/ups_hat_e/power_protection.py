from __future__ import annotations

import logging
import time

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .const import (
    CONF_CRITICAL_DELAY,
    CONF_CRITICAL_PERCENT,
    CONF_EMERGENCY_DELAY,
    CONF_EMERGENCY_PERCENT,
    CONF_NOTIFY_ON_BATTERY,
    CONF_SHUTDOWN_ENABLED,
    OPTION_DEFAULTS,
    SHUTDOWN_GRACE_SECONDS,
)
from .coordinator import UpsHatCoordinator
from .i2c import UpsSnapshot

_LOGGER = logging.getLogger(__name__)

NOTIFICATION_ID = "ups_hat_e_power"


class PowerProtectionManager:
    """Notifies on mains loss and shuts the host down when the battery runs low.

    Only fresh, successful readings are evaluated, so an unavailable or stale
    UPS can never trigger a shutdown.
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator: UpsHatCoordinator
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._low_since: dict[str, float] = {}
        self._was_discharging = False
        self._shutdown_requested = False
        self._cancel_timer: CALLBACK_TYPE | None = None
        self._remove_listener: CALLBACK_TYPE | None = None

    def _option(self, key: str):
        return self._entry.options.get(key, OPTION_DEFAULTS[key])

    @callback
    def async_start(self) -> None:
        self._remove_listener = self._coordinator.async_add_listener(
            self._handle_update
        )

    @callback
    def async_stop(self) -> None:
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
        self._cancel_pending_shutdown()

    def _cancel_pending_shutdown(self) -> None:
        if self._cancel_timer:
            self._cancel_timer()
            self._cancel_timer = None

    @callback
    def _handle_update(self) -> None:
        if not self._coordinator.last_update_success:
            return
        data: UpsSnapshot = self._coordinator.data
        if not 0 <= data.battery_percent <= 100:
            return

        discharging = data.state == "discharging"
        if discharging and not self._was_discharging and self._option(
            CONF_NOTIFY_ON_BATTERY
        ):
            persistent_notification.async_create(
                self._hass,
                f"Mains power lost. Battery at {data.battery_percent}% "
                f"({data.battery_current_ma} mA).",
                title="UPS on battery",
                notification_id=f"{NOTIFICATION_ID}_battery",
            )
        self._was_discharging = discharging

        critical = discharging and data.battery_percent < self._option(
            CONF_CRITICAL_PERCENT
        )
        emergency = (
            not data.vbus_present
            and data.battery_percent < self._option(CONF_EMERGENCY_PERCENT)
        )
        now = time.monotonic()
        triggered = None
        for name, active, delay_key in (
            ("critical", critical, CONF_CRITICAL_DELAY),
            ("emergency", emergency, CONF_EMERGENCY_DELAY),
        ):
            if not active:
                self._low_since.pop(name, None)
                continue
            since = self._low_since.setdefault(name, now)
            if now - since >= self._option(delay_key):
                triggered = name

        if not critical and not emergency:
            self._shutdown_requested = False
            self._cancel_pending_shutdown()
            return
        if triggered:
            self._request_shutdown(triggered, data.battery_percent)

    def _request_shutdown(self, level: str, percent: int) -> None:
        if self._shutdown_requested or not self._option(CONF_SHUTDOWN_ENABLED):
            return
        self._shutdown_requested = True
        _LOGGER.warning(
            "UPS %s battery level (%s%%): shutting down the host in %s seconds",
            level,
            percent,
            SHUTDOWN_GRACE_SECONDS,
        )
        persistent_notification.async_create(
            self._hass,
            f"Battery at {percent}% while on battery. Shutting down the host in "
            f"{SHUTDOWN_GRACE_SECONDS} seconds.",
            title=f"UPS {level} battery",
            notification_id=f"{NOTIFICATION_ID}_shutdown",
        )
        self._cancel_timer = async_call_later(
            self._hass, SHUTDOWN_GRACE_SECONDS, self._async_shutdown
        )

    async def _async_shutdown(self, _now) -> None:
        self._cancel_timer = None
        if not self._hass.services.has_service("hassio", "host_shutdown"):
            _LOGGER.error("hassio.host_shutdown is not available; cannot shut down")
            return
        await self._hass.services.async_call(
            "hassio", "host_shutdown", blocking=False
        )
