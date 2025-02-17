"""Constants for the Mazda Connected Services integration."""

DOMAIN = "mazda_cs"

DATA_CLIENT = "mazda_client"
DATA_COORDINATOR = "coordinator"
DATA_REGION = "region"
DATA_VEHICLES = "vehicles"

# Configuration and Options
CONF_REFRESH_INTERVAL = "refresh_interval"  # Global refresh interval
CONF_VEHICLE_INTERVAL = "vehicle_interval"  # Delay between processing each vehicle
CONF_ENDPOINT_INTERVAL = "endpoint_interval"  # Delay between API calls for same vehicle
CONF_OPTIONS = "options"

MAZDA_REGIONS = {"MNAO": "North America", "MME": "Europe", "MJO": "Japan"}
