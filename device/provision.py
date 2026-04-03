"""Fleet Provisioning: use claim cert to obtain device cert."""

import json
import os
import sys
import threading
from awsiot import mqtt_connection_builder
from awscrt import mqtt
import config
from region_selector import get_endpoint


def provision_device(thing_name: str):
    """Connect with claim cert, request provisioning, save device cert."""

    if os.path.exists(config.DEVICE_CERT) and os.path.exists(config.DEVICE_KEY):
        print(f"Device cert already exists, skipping provisioning.")
        return True

    endpoint, region = get_endpoint()
    print(f"Starting Fleet Provisioning for: {thing_name} (region: {region})")

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=endpoint,
        cert_filepath=config.CLAIM_CERT,
        pri_key_filepath=config.CLAIM_KEY,
        ca_filepath=config.ROOT_CA,
        client_id=f"provision-{thing_name}",
        clean_session=True,
    )

    connect_future = mqtt_connection.connect()
    connect_future.result(timeout=10)
    print("Connected with claim certificate.")

    result = {"done": False, "success": False}
    create_keys_accepted = "$aws/certificates/create/json/accepted"
    create_keys_rejected = "$aws/certificates/create/json/rejected"
    register_accepted = f"$aws/provisioning-templates/{config.PROVISIONING_TEMPLATE}/provision/json/accepted"
    register_rejected = f"$aws/provisioning-templates/{config.PROVISIONING_TEMPLATE}/provision/json/rejected"

    cert_ownership_token = None
    event = threading.Event()

    def on_keys_accepted(topic, payload, **kwargs):
        nonlocal cert_ownership_token
        response = json.loads(payload)
        print("Received new device certificate.")
        os.makedirs("certs", exist_ok=True)
        with open(config.DEVICE_CERT, "w") as f:
            f.write(response["certificatePem"])
        with open(config.DEVICE_KEY, "w") as f:
            f.write(response["privateKey"])

        cert_ownership_token = response["certificateOwnershipToken"]
        register_payload = json.dumps({
            "certificateOwnershipToken": cert_ownership_token,
            "parameters": {
                "ThingName": thing_name,
                "SerialNumber": thing_name,
            }
        })
        mqtt_connection.publish(
            f"$aws/provisioning-templates/{config.PROVISIONING_TEMPLATE}/provision/json",
            register_payload,
            mqtt.QoS.AT_LEAST_ONCE,
        )

    def on_keys_rejected(topic, payload, **kwargs):
        print(f"CreateKeysAndCertificate rejected: {payload}")
        result["done"] = True
        event.set()

    def on_register_accepted(topic, payload, **kwargs):
        response = json.loads(payload)
        print(f"Provisioning successful! ThingName: {response.get('thingName')}")
        result["done"] = True
        result["success"] = True
        event.set()

    def on_register_rejected(topic, payload, **kwargs):
        print(f"RegisterThing rejected: {payload}")
        result["done"] = True
        event.set()

    mqtt_connection.subscribe(create_keys_accepted, mqtt.QoS.AT_LEAST_ONCE, on_keys_accepted).result()
    mqtt_connection.subscribe(create_keys_rejected, mqtt.QoS.AT_LEAST_ONCE, on_keys_rejected).result()
    mqtt_connection.subscribe(register_accepted, mqtt.QoS.AT_LEAST_ONCE, on_register_accepted).result()
    mqtt_connection.subscribe(register_rejected, mqtt.QoS.AT_LEAST_ONCE, on_register_rejected).result()

    mqtt_connection.publish("$aws/certificates/create/json", "{}", mqtt.QoS.AT_LEAST_ONCE)
    print("Requested new keys and certificate...")

    event.wait(timeout=30)
    mqtt_connection.disconnect().result()

    if result["success"]:
        print("Fleet Provisioning completed. Device cert saved.")
    else:
        print("Fleet Provisioning failed.")
        for f in [config.DEVICE_CERT, config.DEVICE_KEY]:
            if os.path.exists(f):
                os.remove(f)

    return result["success"]


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "test-device-001"
    provision_device(name)
