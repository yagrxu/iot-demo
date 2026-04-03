"""Edge device configuration. Connects to Gateway via local TCP."""

import os

# Gateway local address (overridable via env for Docker)
GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "9500"))

# Report interval in seconds
REPORT_INTERVAL = 5
