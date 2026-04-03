"""IoT Gateway: bridges edge devices to AWS IoT Core.

- Provisions itself as an IoT Thing via Fleet Provisioning
- Runs a local TCP server for edge devices to connect
- When an edge device registers, requests cloud Lambda to create the Thing
- Proxies edge device shadow updates to IoT Core
- Forwards shadow delta (desired state changes) back to edge devices
"""

import json
import socket
import threading
from awsiot import mqtt_connection_builder, iotshadow
from awscrt import mqtt
import config
from provision import provision_gateway

REGISTER_TOPIC = f"gateway/{config.GATEWAY_THING_NAME}/edge/register"
REGISTER_REPLY_TOPIC = f"gateway/{config.GATEWAY_THING_NAME}/edge/register/reply"


class Gateway:
    def __init__(self):
        self.mqtt_connection = None
        self.shadow_client = None
        # thingName -> socket mapping for connected edge devices
        self.edge_devices: dict[str, socket.socket] = {}
        # thingName -> threading.Event for registration confirmation
        self.pending_registrations: dict[str, threading.Event] = {}
        self.registration_results: dict[str, dict] = {}
        self.lock = threading.Lock()

    def start(self):
        if not provision_gateway():
            print("Gateway provisioning failed.")
            return

        print(f"Connecting gateway {config.GATEWAY_THING_NAME} to IoT Core...")
        self.mqtt_connection = mqtt_connection_builder.mtls_from_path(
            endpoint=config.IOT_ENDPOINT,
            cert_filepath=config.DEVICE_CERT,
            pri_key_filepath=config.DEVICE_KEY,
            ca_filepath=config.ROOT_CA,
            client_id=config.GATEWAY_THING_NAME,
            clean_session=True,
        )
        self.mqtt_connection.connect().result(timeout=10)
        print("Gateway connected to IoT Core.")

        self.shadow_client = iotshadow.IotShadowClient(self.mqtt_connection)

        # Subscribe to edge registration reply topic
        self.mqtt_connection.subscribe(
            REGISTER_REPLY_TOPIC, mqtt.QoS.AT_LEAST_ONCE,
            self._on_register_reply,
        ).result()
        print(f"[GW] Subscribed to {REGISTER_REPLY_TOPIC}")

        self._start_tcp_server()

    def _on_register_reply(self, topic, payload, **kwargs):
        """Handle registration reply from cloud Lambda."""
        response = json.loads(payload)
        thing_name = response.get("thingName")
        print(f"[GW] Registration reply for {thing_name}: {response.get('status')}")

        with self.lock:
            self.registration_results[thing_name] = response
            event = self.pending_registrations.get(thing_name)
        if event:
            event.set()

    def _register_edge_thing(self, thing_name: str) -> bool:
        """Request cloud to create Thing for edge device. Returns True on success."""
        event = threading.Event()
        with self.lock:
            self.pending_registrations[thing_name] = event

        # Publish registration request
        payload = json.dumps({"thingName": thing_name})
        self.mqtt_connection.publish(REGISTER_TOPIC, payload, mqtt.QoS.AT_LEAST_ONCE)
        print(f"[GW] Requested Thing registration for {thing_name}")

        # Wait for reply
        if not event.wait(timeout=15):
            print(f"[GW] Registration timeout for {thing_name}")
            with self.lock:
                self.pending_registrations.pop(thing_name, None)
            return False

        with self.lock:
            self.pending_registrations.pop(thing_name, None)
            result = self.registration_results.pop(thing_name, {})

        if result.get("status") == "ok":
            print(f"[GW] Thing {thing_name} registered successfully (created={result.get('created')})")
            return True
        else:
            print(f"[GW] Thing {thing_name} registration failed: {result.get('error')}")
            return False

    def _start_tcp_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", config.LOCAL_PORT))
        server.listen(10)
        print(f"Gateway TCP server listening on port {config.LOCAL_PORT}")

        try:
            while True:
                client_sock, addr = server.accept()
                print(f"Edge device connected from {addr}")
                t = threading.Thread(target=self._handle_edge, args=(client_sock, addr), daemon=True)
                t.start()
        except KeyboardInterrupt:
            print("\nGateway shutting down...")
        finally:
            server.close()
            self.mqtt_connection.disconnect().result()

    def _handle_edge(self, sock: socket.socket, addr):
        """Handle a single edge device connection."""
        thing_name = None
        registered = False
        buf = ""
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data.decode()
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    if not line.strip():
                        continue
                    msg = json.loads(line)
                    msg_type = msg.get("type")

                    if msg_type == "register":
                        thing_name = msg["thingName"]
                        print(f"[GW] Edge device {thing_name} requesting registration...")

                        # Register Thing in cloud via Lambda
                        if self._register_edge_thing(thing_name):
                            registered = True
                            with self.lock:
                                self.edge_devices[thing_name] = sock
                            self._subscribe_delta(thing_name)
                            # Notify edge device
                            reply = json.dumps({"type": "registered", "status": "ok"}) + "\n"
                            sock.sendall(reply.encode())
                        else:
                            reply = json.dumps({"type": "registered", "status": "error"}) + "\n"
                            sock.sendall(reply.encode())

                    elif msg_type == "report" and thing_name and registered:
                        self._proxy_shadow_update(thing_name, msg["state"])

        except Exception as e:
            print(f"[GW] Edge handler error ({thing_name or addr}): {e}")
        finally:
            if thing_name:
                with self.lock:
                    self.edge_devices.pop(thing_name, None)
                if registered:
                    self._proxy_shadow_update(thing_name, {"status": "offline"})
                print(f"[GW] Edge device disconnected: {thing_name}")
            sock.close()

    def _proxy_shadow_update(self, thing_name: str, state: dict):
        """Proxy edge device state to IoT Core shadow."""
        request = iotshadow.UpdateShadowRequest(
            thing_name=thing_name,
            state=iotshadow.ShadowState(reported=state),
        )
        self.shadow_client.publish_update_shadow(request, mqtt.QoS.AT_LEAST_ONCE)
        print(f"[GW] Proxied shadow update for {thing_name}: {json.dumps(state)}")

    def _subscribe_delta(self, thing_name: str):
        """Subscribe to shadow delta for an edge device, forward commands."""
        def on_delta(event):
            print(f"[GW] Delta for {thing_name}: {event.state}")
            self._forward_to_edge(thing_name, event.state)

        self.shadow_client.subscribe_to_shadow_delta_updated_events(
            request=iotshadow.ShadowDeltaUpdatedSubscriptionRequest(thing_name=thing_name),
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_delta,
        ).result()
        print(f"[GW] Subscribed to delta for {thing_name}")

    def _forward_to_edge(self, thing_name: str, state: dict):
        """Forward desired state change to the edge device via TCP."""
        with self.lock:
            sock = self.edge_devices.get(thing_name)
        if sock:
            try:
                msg = json.dumps({"type": "delta", "state": state}) + "\n"
                sock.sendall(msg.encode())
            except Exception as e:
                print(f"[GW] Failed to forward to {thing_name}: {e}")
        else:
            print(f"[GW] Edge device {thing_name} not connected, cannot forward delta")


if __name__ == "__main__":
    gw = Gateway()
    gw.start()
