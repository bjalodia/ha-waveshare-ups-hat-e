# Waveshare UPS HAT (E) for Home Assistant

A native Home Assistant custom integration that reads the
[Waveshare UPS HAT (E)](https://www.waveshare.com/wiki/UPS_HAT_(E)) directly over
I²C. It needs no add-on, Docker, MQTT or broker.

Tested on Home Assistant OS 2026.10.4 (Python 3.14, 64-bit) on a Raspberry Pi 3.

## Requirements

- I²C enabled on the Raspberry Pi (see below), with the bus exposed as `/dev/i2c-<n>` (normally `/dev/i2c-1`).
- UPS HAT (E) at I²C address `0x2D` (the default).
- `smbus2==0.6.1`, installed automatically by Home Assistant. Versions older than
  0.6.0 fail on Python 3.14 (64-bit) with `SystemError: buffer overflow`.

## Enable I²C on Home Assistant OS

On Home Assistant OS, I²C is **disabled by default** and cannot be enabled from
inside Home Assistant (there is no `raspi-config`). Edit the boot partition instead:

1. Shut down Home Assistant, power off the Pi, remove the SD card and insert it
   into your computer.
2. Open the partition named `hassos-boot`.
3. Edit `config.txt` in its root and add these lines at the end:

   ```
   dtparam=i2c_vc=on
   dtparam=i2c_arm=on
   ```

4. Load the I²C kernel module. In the root of `hassos-boot`, create a folder
   `CONFIG`, inside it a folder `modules`, and inside that a text file named
   `rpi-i2c.conf` containing:

   ```
   i2c-dev
   ```

5. Eject the card safely, put it back in the Pi and boot.

Afterwards `/dev/i2c-1` should exist (verify with the SSH add-on: `ls /dev/i2c*`).
Then follow the install steps below.

## Install

### Option A: HACS (custom repository)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bjalodia&repository=ha-waveshare-ups-hat-e&category=integration)

Download it from HACS, then restart Home Assistant and continue at step 3 below.

### Option B: Manual

1. Copy the `custom_components/ups_hat_e` folder into `<config>/custom_components/`.
2. Restart Home Assistant.
3. Add the integration with this My button:

   [![Add integration to your Home Assistant instance.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=ups_hat_e)

   The button only works after steps 1 and 2, because the integration has to be
   installed first.

   **Manual steps** (if the button doesn't work):
   - Go to **[Settings → Devices & services](https://my.home-assistant.io/redirect/integrations/)**.
   - Select **[Add integration](https://my.home-assistant.io/redirect/config_flow_start/?domain=ups_hat_e)** in the bottom right corner.
   - Search for **Waveshare UPS HAT (E)** and select it.
   - Choose the I²C bus number (numeric box with up/down buttons, default `1`).

Setup checks that the device at `0x2D` returns module ID `0x0A`. If it does not,
the form reports `not_ups_hat`. If the bus cannot be read, it reports `cannot_connect`.

## Entities

The integration polls every 30 seconds. If a read fails, all entities become
unavailable and the error is logged. Entity IDs look like
`sensor.waveshare_ups_hat_e_ups_battery_percent`.

| Sensor | Source register | Notes |
|---|---|---|
| UPS Battery Voltage | 0x20 | V |
| UPS Battery Current | 0x22 | mA, signed: positive charging, negative discharging |
| UPS Battery Percent | 0x24 | % |
| UPS Remaining Capacity | 0x26 | mAh |
| UPS VBUS Voltage | 0x10 | V |
| UPS VBUS Current | 0x12 | mA |
| UPS VBUS Power | 0x14 | mW |
| UPS State | 0x02 + battery current | `fast_charging`, `charging`, `trickle_charging`, `charging_pending`, `full`, `charge_timeout`, `discharging`, `not_charging`, `standby`, `unknown` |
| UPS Charge Stage | 0x02 bits 0-2 | `standby`, `trickle`, `constant_current`, `constant_voltage`, `pending`, `full`, `timeout` |
| UPS Time To Empty | 0x28 | Text such as `1 h 5 min`. Unknown unless discharging (device reports 0xFFFF) |
| UPS Time To Full | 0x2A | Text such as `45 min`. Unknown when the device has no estimate (0xFFFF) |
| UPS Cell 1-4 Voltage | 0x30-0x36 | mV |
| UPS Cell Imbalance | derived | Max minus min cell voltage in mV. Unavailable if any cell reads 0 |
| UPS Chip Communication (diagnostic) | 0x03 | `ok`, `bq4050_error`, `ip2368_error`, `bq4050_and_ip2368_error`. The `raw_register_0x03` attribute holds the raw bits |
| UPS Software Revision (diagnostic) | 0x50 | Register value divided by 10, for example `0x14` shows `2.0` |

State decoding follows the vendor register map for register 0x02: bit 7 charging,
bit 6 fast charging, bit 5 VBUS powered, bits 0-2 charge sub-state.

## Power protection (built in)

The integration replaces the separate automations. It shuts the host down and
notifies by itself, using only fresh, successful readings: if the UPS is
unavailable or a read fails, nothing is triggered.

- **Critical:** the UPS is discharging and the battery has been below the critical
  level (default 12%) for the delay (default 120 s).
- **Emergency:** there is no external power (VBUS absent) and the battery has been
  below the emergency level (default 5%) for the delay (default 30 s).
- **Shutdown:** a persistent notification is created, then `hassio.host_shutdown`
  is called after 15 seconds. A pending shutdown is cancelled if the condition clears.
- **On battery:** a persistent notification when the UPS switches to discharging.

Change the thresholds, delays, notification and the on/off switch under
**Settings → Devices & services → Waveshare UPS HAT (E) → Configure**.
Automatic shutdown is on by default. Polling is every 30 seconds, so delays are
effectively rounded up to the next poll. This needs the Supervisor
(`hassio.host_shutdown`), as on Home Assistant OS.

Test the thresholds safely, for example by temporarily raising the critical level
while on battery, before relying on them.

## Project layout

```
custom_components/ups_hat_e/
  __init__.py          setup and unload
  config_flow.py       UI setup (bus selection) and the Configure (options) dialog
  const.py             constants and option defaults
  coordinator.py       30-second polling coordinator
  i2c.py               register reads and state decoding
  sensor.py            sensor entities
  power_protection.py  notifications and automatic shutdown
  translations/en.json UI text
  manifest.json        metadata and smbus2 requirement
  brand/               icon and logo
configuration.yaml
automations.yaml       empty (no UPS automations needed)
```

## Troubleshooting

- `cannot_connect` when adding: check that `/dev/i2c-<n>` exists, I²C is enabled,
  and `smbus2` is 0.6.0 or newer. Details are in the Home Assistant log.
- Time to empty and time to full show unknown: expected when the device reports no estimate.
- Chip communication shows an error: read the `raw_register_0x03` attribute.
  Bit 1 is the BQ4050 and bit 0 is the IP2368; `0b11` means both are healthy.
