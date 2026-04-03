"""Fleet Provisioning for the gateway itself."""

import json
import os
import threading
from awsiot import mqtt_connection_builder
from awscrt import mqtt
import config


def provision_gateway():
    """Provision the gateway as an IoT Thing."""

    if os.path.exists(config.DEVICE_CERT) and os.path.exists(config.DEVICE_KEY):
        print("Gateway cert already exists, skipping provisioning.")
        return True

    print(f"Starting Fleet Provisioning for gateway: {config.GATEWAY_THING_NAME}")

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
        endpoint=config.IOT_ENDPOINT,
        cert_filepath=config.CLAIM_CERT,
        pri_key_filepath=config.CLAIM_KEY,
        ca_filepath=config.ROOT_CA,
        client_id=f"provision-{config.GATEWAY_THING_NAME}",
        clean_session=True,
    )

    mqtt_connection.connect().result(timeout=10)
    print("Connected with claim certificate.")

    result = {"done": False, "success": False}
    event = threading.Event()

    def on_keys_accepted(topic, payload, **kwargs):
        response = json.loads(payload)
        print("Received gateway certificate.")
        os.makedirs("certs", exist_ok=True)
        with open(config.DEVICE_CERT, "w") as f:
            f.write(response["certificatePem"])
        with open(config.DEVICE_KEY, "w") as f:
            f.write(response["privateKey"])

        register_payload = json.dumps({
            "certificateOwnershipToken": response["certificateOwnershipToken"],
            "parameters": {
                "ThingName": config.GATEWAY_THING_NAME,
                "SerialNumber": config.GATEWAY_THING_NAME,
            }
        })
        mqtt_connection.publish(
            f"$aws/provisioning-templates/{config.PROVISIONING_TEMPLATE}/provision/json",
            register_payload, mqtt.QoS.AT_LEAST_ONCE,
        )

    def on_keys_rejected(topic, payload, **kwargs):
        print(f"CreateKeysAndCertificate rejected: {payload}")
        result["done"] = True
        event.set()

    def on_register_accepted(topic, payload, **kwargs):
        print(f"Gateway provisioning successful!")
        result["done"] = True
        result["success"] = True
        event.set()

    def on_register_rejected(topic, payload, **kwargs):
        print(f"RegisterThing rejected: {payload}")
        result["done"] = True
        event.set()

    template = config.PROVISIONING_TEMPLATE
    mqtt_connection.subscribe("$aws/certificates/create/json/accepted", mqtt.QoS.AT_LEAST_ONCE, on_keys_accepted).result()
    mqtt_connection.subscribe("$aws/certificates/create/json/rejected", mqtt.QoS.AT_LEAST_ONCE, on_keys_rejected).result()
    mqtt_connection.subscribe(f"$aws/provisioning-templates/{template}/provision/json/accepted", mqtt.QoS.AT_LEAST_ONCE, on_register_accepted).result()
    mqtt_connection.subscribe(f"$aws/provisioning-templates/{template}/provision/json/rejected", mqtt.QoS.AT_LEAST_ONCE, on_register_rejected).result()

    mqtt_connection.publish("$aws/certificates/create/json", "{}", mqtt.QoS.AT_LEAST_ONCE)
    print("Requested new keys and certificate...")

    event.wait(timeout=30)
    mqtt_connection.disconnect().result()

    if not result["success"]:
        for f in [config.DEVICE_CERT, config.DEVICE_KEY]:
            if os.path.exists(f):
                os.remove(f)

    return result["success"]


if __name__ == "__main__":
    provision_gateway()
