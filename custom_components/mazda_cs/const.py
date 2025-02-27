"""Constants for the Mazda Connected Services integration."""

DOMAIN = "mazda_cs"

# Configuration and Options
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_REGION = "region"
CONF_REFRESH_INTERVAL = "refresh_interval"  # Global refresh interval
CONF_VEHICLE_INTERVAL = "vehicle_interval"  # Delay between processing each vehicle
CONF_ENDPOINT_INTERVAL = "endpoint_interval"  # Delay between API calls for same vehicle
CONF_HEALTH_REPORT_INTERVAL = "health_report_interval"  # Interval for health report updates
CONF_HEALTH_VEHICLE_INTERVAL = "health_vehicle_interval"
CONF_OPTIONS = "options"

# New configuration options for testing and debugging
CONF_DEBUG_MODE = "debug_mode"
CONF_LOG_RESPONSES = "log_responses"
CONF_TESTING_MODE = "testing_mode"
CONF_ENABLE_METRICS = "enable_metrics"

# Default values (in seconds)
DEFAULT_REFRESH_INTERVAL = 15 * 60  # 15 minutes in seconds
DEFAULT_VEHICLE_INTERVAL = 2
DEFAULT_ENDPOINT_INTERVAL = 1
DEFAULT_HEALTH_REPORT_INTERVAL = 60 * 60  # 60 minutes in seconds
DEFAULT_HEALTH_VEHICLE_INTERVAL = 30

# Data storage keys
DATA_CLIENT = "mazda_client"
DATA_COORDINATOR = "coordinator"
DATA_HEALTH_COORDINATOR = "health_coordinator"
DATA_REGION = "region"
DATA_VEHICLES = "vehicles"
DATA_EMAIL = "email"
DATA_PASSWORD = "password"

MAZDA_REGIONS = {"MNAO": "North America", "MME": "Europe", "MJO": "Japan"}
