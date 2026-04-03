"""Region configuration via BLE (Bluetooth Low Energy) provisioning.

In production, the mobile app connects to the device via BLE and writes
the region info. This module provides the interface and a CLI simulator.
"""

import os
import json
import config

BLE_CONFIG_FILE = "certs/.ble_config.json"


def set_region_via_ble(region: str):
    """Called when mobile app writes region info over BLE.

    In production this would be triggered by a BLE GATT write characteristic.
    The mobile app determines the user's region and sends it to the device
    during the initial Bluetooth pairing/setup flow.
    """
    if region not in config.REGION_ENDPOINTS:
        raise ValueError(f"Unknown region: {region}. Available: {list(config.REGION_ENDPOINTS.keys())}")

    os.makedirs(os.path.dirname(BLE_CONFIG_FILE), exist_ok=True)
    ble_config = {}
    if os.path.exists(BLE_CONFIG_FILE):
        with open(BLE_CONFIG_FILE) as f:
            ble_config = json.load(f)

    ble_config["region"] = region
    with open(BLE_CONFIG_FILE, "w") as f:
        json.dump(ble_config, f)

    print(f"[BLE] Region set to: {region}")


def get_region() -> str:
    """Read the region configured via BLE. Raises if not yet configured."""
    if not os.path.exists(BLE_CONFIG_FILE):
        raise RuntimeError("Region not configured. Device must be set up via BLE first.")

    with open(BLE_CONFIG_FILE) as f:
        ble_config = json.load(f)

    region = ble_config.get("region")
    if not region or region not in config.REGION_ENDPOINTS:
        raise RuntimeError(f"Invalid region in BLE config: {region}")

    return region


def get_endpoint() -> tuple[str, str]:
    """Return (endpoint, region) from BLE config."""
    region = get_region()
    return config.REGION_ENDPOINTS[region], region
