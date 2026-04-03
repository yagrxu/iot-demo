"""Simulate the mobile app BLE provisioning flow.

Usage:
    python ble_simulator.py <region>

Example:
    python ble_simulator.py ap-northeast-1
"""

import sys
import config
from region_selector import set_region_via_ble


def main():
    if len(sys.argv) < 2:
        print("Usage: python ble_simulator.py <region>")
        print(f"Available regions: {list(config.REGION_ENDPOINTS.keys())}")
        sys.exit(1)

    region = sys.argv[1]
    print(f"[BLE Simulator] Mobile app connecting to device...")
    print(f"[BLE Simulator] Writing region: {region}")
    set_region_via_ble(region)
    print(f"[BLE Simulator] Device configured. Ready for provisioning.")


if __name__ == "__main__":
    main()
