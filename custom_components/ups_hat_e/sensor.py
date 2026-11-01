from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .coordinator import UpsHatCoordinator
from .i2c import UpsSnapshot


def _format_minutes(total: int) -> str:
    days, remainder = divmod(total, 1440)
    hours, minutes = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if minutes or not parts:
        parts.append(f"{minutes} min")
    return " ".join(parts)


@dataclass(frozen=True, kw_only=True)
class UpsSensorDescription(SensorEntityDescription):
    value_key: str


SENSORS: tuple[UpsSensorDescription, ...] = (
    UpsSensorDescription(
        key="battery_voltage",
        value_key="battery_voltage_mv",
        name="UPS Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    UpsSensorDescription(
        key="battery_current",
        value_key="battery_current_ma",
        name="UPS Battery Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement="mA",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    UpsSensorDescription(
        key="battery_percent",
        value_key="battery_percent",
        name="UPS Battery Percent",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    UpsSensorDescription(
        key="remaining_capacity",
        value_key="remaining_capacity_mah",
        name="UPS Remaining Capacity",
        native_unit_of_measurement="mAh",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    UpsSensorDescription(
        key="vbus_voltage",
        value_key="vbus_voltage_mv",
        name="UPS VBUS Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement="V",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    UpsSensorDescription(
        key="state",
        value_key="state",
        name="UPS State",
    ),
    UpsSensorDescription(
        key="vbus_current",
        value_key="vbus_current_ma",
        name="UPS VBUS Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement="mA",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    UpsSensorDescription(
        key="vbus_power",
        value_key="vbus_power_mw",
        name="UPS VBUS Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement="mW",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    UpsSensorDescription(
        key="time_to_empty",
        value_key="time_to_empty_min",
        name="UPS Time To Empty",
    ),
    UpsSensorDescription(
        key="time_to_full",
        value_key="time_to_full_min",
        name="UPS Time To Full",
    ),
    *(
        UpsSensorDescription(
            key=f"cell_{index}_voltage",
            value_key=f"cell_{index}_voltage_mv",
            name=f"UPS Cell {index} Voltage",
            device_class=SensorDeviceClass.VOLTAGE,
            native_unit_of_measurement="mV",
            state_class=SensorStateClass.MEASUREMENT,
        )
        for index in range(1, 5)
    ),
    UpsSensorDescription(
        key="cell_imbalance",
        value_key="cell_imbalance",
        name="UPS Cell Imbalance",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement="mV",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    UpsSensorDescription(
        key="charge_stage",
        value_key="charge_stage",
        name="UPS Charge Stage",
    ),
    UpsSensorDescription(
        key="communication",
        value_key="communication",
        name="UPS Chip Communication",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    UpsSensorDescription(
        key="software_revision",
        value_key="software_revision",
        name="UPS Software Revision",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: UpsHatCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        UpsHatSensor(coordinator, entry, description) for description in SENSORS
    )


class UpsHatSensor(CoordinatorEntity[DataUpdateCoordinator[UpsSnapshot]], SensorEntity):
    entity_description: UpsSensorDescription

    def __init__(
        self,
        coordinator: UpsHatCoordinator,
        entry: ConfigEntry,
        description: UpsSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Waveshare",
            model="UPS HAT (E)",
            sw_version=coordinator.data.software_revision,
        )

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self.entity_description.key != "communication":
            return None
        return {"raw_register_0x03": f"0b{self.coordinator.data.communication_raw:08b}"}

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        if self.entity_description.key != "cell_imbalance":
            return True
        return all(
            cell > 0
            for cell in (
                self.coordinator.data.cell_1_voltage_mv,
                self.coordinator.data.cell_2_voltage_mv,
                self.coordinator.data.cell_3_voltage_mv,
                self.coordinator.data.cell_4_voltage_mv,
            )
        )

    @property
    def native_value(self) -> int | float | str | None:
        if self.entity_description.value_key == "cell_imbalance":
            cells = (
                self.coordinator.data.cell_1_voltage_mv,
                self.coordinator.data.cell_2_voltage_mv,
                self.coordinator.data.cell_3_voltage_mv,
                self.coordinator.data.cell_4_voltage_mv,
            )
            if any(cell <= 0 for cell in cells):
                return None
            return max(cells) - min(cells)

        value = getattr(self.coordinator.data, self.entity_description.value_key)
        if self.entity_description.key in {"time_to_empty", "time_to_full"}:
            if value == 0xFFFF:
                return None
            return _format_minutes(value)
        if self.entity_description.key in {"battery_voltage", "vbus_voltage"}:
            return round(value / 1000, 2)
        return value
