"""Shadow client: connect with device cert, report shadow state."""

import json
import sys
import time
import random
from awsiot import mqtt_connection_builder, iotshadow
from awscrt import mqtt
import config
from provision import provision_device
from region_selector import get_endpoint


def run_shadow_client(thing_name: str):
    """Connect with device cert and periodically update shadow."""

    if not provision_device(thing_name):
        print("Provisioning failed, cannot start shadow client.")
        return

    endpoint, region = get_endpoint()
    print(f"Connecting as {thing_name} to {region}...")

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=endpoint,
        cert_filepath=config.DEVICE_CERT,
        pri_key_filepath=config.DEVICE_KEY,
        ca_filepath=config.ROOT_CA,
        client_id=thing_name,
        clean_session=True,
    )

    mqtt_connection.connect().result(timeout=10)
    print("Connected with device certificate.")

    shadow_client = iotshadow.IotShadowClient(mqtt_connection)

    def on_shadow_delta(event):
        print(f"Shadow delta received: {event.state}")
        report_state(shadow_client, thing_name, event.state)

    shadow_client.subscribe_to_shadow_delta_updated_events(
        request=iotshadow.ShadowDeltaUpdatedSubscriptionRequest(thing_name=thing_name),
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_shadow_delta,
    ).result()

    print("Starting shadow updates (Ctrl+C to stop)...")
    try:
        while True:
            state = {
                "temperature": round(20 + random.random() * 15, 1),
                "humidity": round(40 + random.random() * 40, 1),
                "firmware": "1.0.0",
                "status": "online",
            }
            report_state(shadow_client, thing_name, state)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        mqtt_connection.disconnect().result()
        print("Disconnected.")


def report_state(shadow_client, thing_name, state):
    """Report device state to shadow."""
    request = iotshadow.UpdateShadowRequest(
        thing_name=thing_name,
        state=iotshadow.ShadowState(reported=state),
    )
    shadow_client.publish_update_shadow(request, mqtt.QoS.AT_LEAST_ONCE)
    print(f"Reported: {json.dumps(state)}")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "test-device-001"
    run_shadow_client(name)
