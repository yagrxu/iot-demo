"""Edge device that connects to Gateway via local TCP.

The edge device sends sensor data to the gateway, which proxies it to IoT Core.
It also receives desired state changes (commands) from the gateway.

Protocol (newline-delimited JSON):
  -> {"type":"register","thingName":"edge-sensor-01"}
  <- {"type":"registered","status":"ok"}
  -> {"type":"report","state":{"temperature":25.1,...}}
  <- {"type":"delta","state":{"power":true,...}}
"""

import json
import socket
import sys
import time
import random
import threading
import config


def run_edge_device(thing_name: str):
    print(f"[{thing_name}] Connecting to gateway at {config.GATEWAY_HOST}:{config.GATEWAY_PORT}...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Retry connection (gateway may not be ready yet in docker-compose)
    for attempt in range(10):
        try:
            sock.connect((config.GATEWAY_HOST, config.GATEWAY_PORT))
            break
        except ConnectionRefusedError:
            print(f"[{thing_name}] Gateway not ready, retrying in 2s... ({attempt + 1}/10)")
            time.sleep(2)
    else:
        print(f"[{thing_name}] Failed to connect to gateway.")
        return

    print(f"[{thing_name}] Connected to gateway.")

    # Register with gateway
    send_msg(sock, {"type": "register", "thingName": thing_name})
    print(f"[{thing_name}] Waiting for registration confirmation...")

    # Wait for registration reply
    buf = ""
    while True:
        data = sock.recv(4096)
        if not data:
            print(f"[{thing_name}] Gateway closed connection during registration.")
            return
        buf += data.decode()
        if "\n" in buf:
            line, buf = buf.split("\n", 1)
            msg = json.loads(line)
            if msg.get("type") == "registered":
                if msg.get("status") == "ok":
                    print(f"[{thing_name}] Registration confirmed. Starting data reporting.")
                    break
                else:
                    print(f"[{thing_name}] Registration failed.")
                    sock.close()
                    return

    # Start listener for commands from gateway
    listener = threading.Thread(target=listen_commands, args=(sock, thing_name, buf), daemon=True)
    listener.start()

    # Periodically report sensor data
    print(f"[{thing_name}] Reporting every {config.REPORT_INTERVAL}s (Ctrl+C to stop)...")
    try:
        while True:
            state = {
                "temperature": round(20 + random.random() * 15, 1),
                "humidity": round(40 + random.random() * 40, 1),
                "firmware": "1.0.0",
                "status": "online",
            }
            send_msg(sock, {"type": "report", "state": state})
            print(f"[{thing_name}] Reported: {json.dumps(state)}")
            time.sleep(config.REPORT_INTERVAL)
    except KeyboardInterrupt:
        print(f"\n[{thing_name}] Stopping...")
    finally:
        sock.close()


def send_msg(sock: socket.socket, msg: dict):
    data = json.dumps(msg) + "\n"
    sock.sendall(data.encode())


def listen_commands(sock: socket.socket, thing_name: str, initial_buf: str = ""):
    """Listen for commands (delta) from gateway."""
    buf = initial_buf
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                print(f"[{thing_name}] Gateway disconnected.")
                break
            buf += data.decode()
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if line.strip():
                    msg = json.loads(line)
                    if msg.get("type") == "delta":
                        print(f"[{thing_name}] Command received: {msg['state']}")
    except Exception as e:
        print(f"[{thing_name}] Listener error: {e}")


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "edge-sensor-01"
    run_edge_device(name)
