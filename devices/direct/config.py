"""Device configuration with multi-region support."""

# Region endpoints mapping (populated after CDK deployment per region)
REGION_ENDPOINTS = {
    "ap-northeast-1": "your-endpoint.iot.ap-northeast-1.amazonaws.com",
    "us-east-1": "your-endpoint.iot.us-east-1.amazonaws.com",
    "eu-west-1": "your-endpoint.iot.eu-west-1.amazonaws.com",
}

# Default region if auto-detection fails
DEFAULT_REGION = "ap-northeast-1"

# Fleet Provisioning template name (same across all regions)
PROVISIONING_TEMPLATE = "FleetProvisioningTemplate"

# Paths for claim certificate (temporary)
CLAIM_CERT = "certs/claim-cert.pem"
CLAIM_KEY = "certs/claim-private.key"
ROOT_CA = "certs/AmazonRootCA1.pem"

# Paths for device certificate (permanent, obtained via provisioning)
DEVICE_CERT = "certs/device-cert.pem"
DEVICE_KEY = "certs/device-private.key"

# Persisted region selection
REGION_FILE = "certs/.region"
