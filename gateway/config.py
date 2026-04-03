"""Gateway configuration."""

# AWS IoT Core endpoint (replace with your endpoint)
IOT_ENDPOINT = "your-endpoint.iot.ap-northeast-1.amazonaws.com"

# Gateway's own thing name
GATEWAY_THING_NAME = "gateway-01"

# Fleet Provisioning template (gateway uses same template)
PROVISIONING_TEMPLATE = "GatewayProvisioningTemplate"

# Certificate paths
CLAIM_CERT = "certs/claim-cert.pem"
CLAIM_KEY = "certs/claim-private.key"
ROOT_CA = "certs/AmazonRootCA1.pem"
DEVICE_CERT = "certs/gateway-cert.pem"
DEVICE_KEY = "certs/gateway-private.key"

# Local TCP server for edge devices
LOCAL_PORT = 9500
