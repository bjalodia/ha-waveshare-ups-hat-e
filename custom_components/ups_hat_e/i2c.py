from __future__ import annotations

from dataclasses import dataclass

from .const import EXPECTED_MODULE_ID, I2C_ADDRESS, MODULE_ID_REGISTER


class InvalidDeviceError(Exception):
    """Raised when the device at the configured I2C address is not the UPS HAT."""


@dataclass(frozen=True)
class UpsSnapshot:
    battery_voltage_mv: int
    battery_current_ma: int
    battery_percent: int
    remaining_capacity_mah: int
    vbus_voltage_mv: int
    state: str
    vbus_current_ma: int
    vbus_power_mw: int
    time_to_empty_min: int
    time_to_full_min: int
    cell_1_voltage_mv: int
    cell_2_voltage_mv: int
    cell_3_voltage_mv: int
    cell_4_voltage_mv: int
    software_revision: str
    vbus_present: bool
    charge_stage: str
    communication: str
    communication_raw: int

CHARGE_STAGES = {
    0: "standby",
    1: "trickle",
    2: "constant_current",
    3: "constant_voltage",
    4: "pending",
    5: "full",
    6: "timeout",
}

def read_device_identity(bus_number: int) -> tuple[int, str]:
    from smbus2 import SMBus

    with SMBus(bus_number) as bus:
        module_id = bus.read_byte_data(I2C_ADDRESS, MODULE_ID_REGISTER)
        if module_id != EXPECTED_MODULE_ID:
            raise InvalidDeviceError(
                f"Unexpected module ID 0x{module_id:02x}; expected 0x{EXPECTED_MODULE_ID:02x}"
            )
        revision = bus.read_byte_data(I2C_ADDRESS, 0x50)

    return module_id, f"{revision / 10:.1f}"


def read_snapshot(bus_number: int) -> UpsSnapshot:
    from smbus2 import SMBus

    with SMBus(bus_number) as bus:
        module_id = bus.read_byte_data(I2C_ADDRESS, MODULE_ID_REGISTER)
        if module_id != EXPECTED_MODULE_ID:
            raise InvalidDeviceError(
                f"Unexpected module ID 0x{module_id:02x}; expected 0x{EXPECTED_MODULE_ID:02x}"
            )

        revision = bus.read_byte_data(I2C_ADDRESS, 0x50)
        status = bus.read_byte_data(I2C_ADDRESS, 0x02)
        comm = bus.read_byte_data(I2C_ADDRESS, 0x03)
        bq4050_ok = bool(comm & 0x02)
        ip2368_ok = bool(comm & 0x01)
        if bq4050_ok and ip2368_ok:
            communication = "ok"
        elif ip2368_ok:
            communication = "bq4050_error"
        elif bq4050_ok:
            communication = "ip2368_error"
        else:
            communication = "bq4050_and_ip2368_error"
        def read_word(register: int) -> int:
            low = bus.read_byte_data(I2C_ADDRESS, register)
            high = bus.read_byte_data(I2C_ADDRESS, register + 1)
            return low | (high << 8)

        def signed_word(register: int) -> int:
            value = read_word(register)
            return value - 0x10000 if value >= 0x8000 else value

        sub_state = status & 0x07
        is_charging = status & 0x80
        is_fast_charging = status & 0x40
        vbus_present = bool(status & 0x20)
        battery_current = signed_word(0x22)
        if sub_state == 5:
            state = "full"
        elif sub_state == 6:
            state = "charge_timeout"
        elif sub_state == 4:
            state = "charging_pending"
        elif battery_current < 0:
            state = "discharging"
        elif battery_current > 0 or is_charging:
            if sub_state == 1:
                state = "trickle_charging"
            elif is_fast_charging:
                state = "fast_charging"
            else:
                state = "charging"
        elif vbus_present:
            state = "not_charging"
        elif sub_state == 0:
            state = "standby"
        else:
            state = "unknown"

        return UpsSnapshot(
            battery_voltage_mv=read_word(0x20),
            battery_current_ma=battery_current,
            battery_percent=read_word(0x24),
            remaining_capacity_mah=read_word(0x26),
            vbus_voltage_mv=read_word(0x10),
            state=state,
            vbus_current_ma=signed_word(0x12),
            vbus_power_mw=read_word(0x14),
            time_to_empty_min=read_word(0x28),
            time_to_full_min=read_word(0x2A),
            cell_1_voltage_mv=read_word(0x30),
            cell_2_voltage_mv=read_word(0x32),
            cell_3_voltage_mv=read_word(0x34),
            cell_4_voltage_mv=read_word(0x36),
            software_revision=f"{revision / 10:.1f}",
            vbus_present=vbus_present,
            charge_stage=CHARGE_STAGES.get(sub_state, "unknown"),
            communication=communication,
            communication_raw=comm,
        )
