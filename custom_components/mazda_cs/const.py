"""Constants for the Mazda Connected Services integration."""

# TPMS Warning Level Definitions
# These are the meanings of the numeric values returned by the Mazda API
# 0 = Normal - No issues detected with tire pressure
# 1 = Warning - Minor pressure deviation from recommended value
# 2 = Low Pressure - Tire pressure significantly below recommended value
# 3 = Critical - Dangerous tire pressure condition or possible TPMS sensor issue
# 4 = System Error - TPMS system malfunction or communication error
# 
# Vehicle-specific TPMS behavior:
# - CX-5 models: Uses a single TPMS sensor for all four tires, so all tires will show identical warnings
# - Other models: May have individual sensors per tire showing different warning states

# TPMS Warning Level Constants
TPMS_WARNING_NORMAL = 0
TPMS_WARNING_WARNING = 1
TPMS_WARNING_LOW_PRESSURE = 2
TPMS_WARNING_CRITICAL = 3
TPMS_WARNING_SYSTEM_ERROR = 4

# TPMS Warning Descriptions
TPMS_WARNING_DESCRIPTIONS = {
    TPMS_WARNING_NORMAL: "Normal",
    TPMS_WARNING_WARNING: "Warning",
    TPMS_WARNING_LOW_PRESSURE: "Low Pressure",
    TPMS_WARNING_CRITICAL: "Critical",
    TPMS_WARNING_SYSTEM_ERROR: "System Error",
}

# Engine Status Definitions
# PowerControlStatus values:
# 0 = Off - Vehicle is completely off
# 1 = On - Vehicle electronics are on but engine is not running
# 2 = Engine Running - Engine is currently running
#
# EngineState values:
# 0 = Initial State - System starting up
# 1 = Engine Off - Engine is off
# 2 = Engine Starting - Engine is in the process of starting
# 3 = Engine Running - Engine is running
# 4 = Engine Stopping - Engine is in the process of stopping

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
CONF_DISCOVERY_MODE = "discovery_mode"  # New flag for sensor discovery
CONF_HEALTH_TIMEOUT = "health_timeout"  # Timeout for health report API calls

# Advanced retry mechanism options
CONF_MAX_RETRIES = "max_retries"  # Maximum number of retry attempts
CONF_RETRY_DELAY = "retry_delay"  # Initial delay between retries in seconds
CONF_MAX_RETRY_BACKOFF = "max_retry_backoff"  # Maximum backoff delay in seconds

# Default values (in seconds)
DEFAULT_REFRESH_INTERVAL = 15 * 60  # 15 minutes in seconds
DEFAULT_VEHICLE_INTERVAL = 2
DEFAULT_ENDPOINT_INTERVAL = 1
DEFAULT_HEALTH_REPORT_INTERVAL = 60  # 60 minutes (stored as minutes)
DEFAULT_HEALTH_VEHICLE_INTERVAL = 30
DEFAULT_HEALTH_TIMEOUT = 45  # Default timeout for health report API calls in seconds

# Default retry mechanism values
DEFAULT_MAX_RETRIES = 3  # Number of retry attempts
DEFAULT_RETRY_DELAY = 1.0  # Initial delay (1 second)
DEFAULT_MAX_RETRY_BACKOFF = 30.0  # Maximum backoff (30 seconds)

# Data storage keys
DATA_CLIENT = "mazda_client"
DATA_COORDINATOR = "coordinator"
DATA_HEALTH_COORDINATOR = "health_coordinator"
DATA_REGION = "region"
DATA_VEHICLES = "vehicles"
DATA_EMAIL = "email"
DATA_PASSWORD = "password"

MAZDA_REGIONS = {"MNAO": "North America", "MME": "Europe", "MJO": "Japan"}

# VIN Prefixes for identifying Mazda models
VIN_PREFIX_CX5 = "JM3KFBBL"  # Mazda CX-5 VIN prefix
VIN_PREFIX_CX30 = "3MVDMBBM"  # Mazda CX-30 VIN prefix  
VIN_PREFIX_MAZDA3 = "3MZBPABM"  # Mazda 3 VIN prefix

# Model-specific health report templates
# These templates define the structure and metadata for sensors based on model type

# Map of VIN prefixes to model templates
MODEL_TEMPLATE_MAP = {
    VIN_PREFIX_MAZDA3: "MAZDA3",
    VIN_PREFIX_CX30: "CX30",
    VIN_PREFIX_CX5: "CX5",
}

# Default fallback template if no matching template is found
DEFAULT_TEMPLATE = "GENERAL"

# General template with common sensors that should work across all models
# This serves as a fallback for unknown models
GENERAL_HEALTH_TEMPLATE = {
    "OdoDispValue": {
        "name": "Odometer",
        "icon": "mdi:counter",
        "device_class": None,
        "state_class": "total_increasing",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "OdoDispValueMile": {
        "name": "Odometer (Miles)",
        "icon": "mdi:counter",
        "device_class": None,
        "state_class": "total_increasing",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    "OccurrenceDate": {
        "name": "Health Report Date",
        "icon": "mdi:calendar-clock",
        "device_class": "timestamp",
        "entity_category": "diagnostic"
    }
}

# Mazda 3 Health Report Template
MAZDA3_HEALTH_TEMPLATE = {
    # Base odometer and timestamp data
    "OdoDispValue": {
        "name": "Odometer",
        "icon": "mdi:counter",
        "device_class": None,
        "state_class": "total_increasing",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "OdoDispValueMile": {
        "name": "Odometer (Miles)",
        "icon": "mdi:counter",
        "device_class": None,
        "state_class": "total_increasing",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    "OccurrenceDate": {
        "name": "Health Report Date",
        "icon": "mdi:calendar-clock",
        "device_class": "timestamp",
        "entity_category": "diagnostic"
    },
    
    # Oil information
    "OilMntInformation.RemOilDistK": {
        "name": "Oil Change Distance Remaining",
        "icon": "mdi:oil",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "OilMntInformation.RemOilDistMile": {
        "name": "Oil Change Distance Remaining (Miles)",
        "icon": "mdi:oil",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    
    # Regular maintenance information
    "RegularMntInformation.RemRegDistKm": {
        "name": "Maintenance Distance Remaining",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "RegularMntInformation.RemRegDistMile": {
        "name": "Maintenance Distance Remaining (Miles)",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    "RegularMntInformation.MntSetDistKm": {
        "name": "Maintenance Interval",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "RegularMntInformation.MntSetDistMile": {
        "name": "Maintenance Interval (Miles)",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    
    # Warning indicators
    "WngOilShortage": {
        "name": "Oil Shortage Warning",
        "icon": "mdi:oil-alert",
        "device_class": None,
        "options": ["Off", "On"],
        "entity_category": "diagnostic"
    },
    "WngOilAmountExceed": {
        "name": "Oil Amount Exceed Warning",
        "icon": "mdi:oil-alert",
        "device_class": None,
        "options": ["Off", "On"],
        "entity_category": "diagnostic"
    },
    "WngTyrePressureLow": {
        "name": "Tire Pressure Low Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Off", "On"],
        "entity_category": "diagnostic"
    }
}

# CX-30 Health Report Template
CX30_HEALTH_TEMPLATE = {
    # Base odometer and timestamp data
    "OdoDispValue": {
        "name": "Odometer",
        "icon": "mdi:counter",
        "device_class": None,
        "state_class": "total_increasing",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "OdoDispValueMile": {
        "name": "Odometer (Miles)",
        "icon": "mdi:counter",
        "device_class": None,
        "state_class": "total_increasing",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    "OccurrenceDate": {
        "name": "Health Report Date",
        "icon": "mdi:calendar-clock",
        "device_class": "timestamp",
        "entity_category": "diagnostic"
    },
    
    # Oil information
    "OilMntInformation.RemOilDistK": {
        "name": "Oil Change Distance Remaining",
        "icon": "mdi:oil",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "OilMntInformation.RemOilDistMile": {
        "name": "Oil Change Distance Remaining (Miles)",
        "icon": "mdi:oil",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    
    # Regular maintenance information
    "RegularMntInformation.RemRegDistMile": {
        "name": "Maintenance Distance Remaining (Miles)",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    "RegularMntInformation.MntSetDistMile": {
        "name": "Maintenance Interval (Miles)",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    "RegularMntInformation.MntSetDistKm": {
        "name": "Maintenance Interval",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    
    # TPMS Information (CX-30 has detailed tire pressure)
    "TPMSInformation.FLTPrsDispPsi": {
        "name": "Front Left Tire Pressure",
        "icon": "mdi:car-tire-alert",
        "device_class": "pressure",
        "state_class": "measurement",
        "unit_of_measurement": "psi",
        "entity_category": "diagnostic"
    },
    "TPMSInformation.FRTPrsDispPsi": {
        "name": "Front Right Tire Pressure",
        "icon": "mdi:car-tire-alert",
        "device_class": "pressure",
        "state_class": "measurement",
        "unit_of_measurement": "psi",
        "entity_category": "diagnostic"
    },
    "TPMSInformation.RLTPrsDispPsi": {
        "name": "Rear Left Tire Pressure",
        "icon": "mdi:car-tire-alert",
        "device_class": "pressure", 
        "state_class": "measurement",
        "unit_of_measurement": "psi",
        "entity_category": "diagnostic"
    },
    "TPMSInformation.RRTPrsDispPsi": {
        "name": "Rear Right Tire Pressure",
        "icon": "mdi:car-tire-alert",
        "device_class": "pressure",
        "state_class": "measurement",
        "unit_of_measurement": "psi",
        "entity_category": "diagnostic"
    },
    "TPMSInformation.FLTPrsDispBar": {
        "name": "Front Left Tire Pressure (Bar)",
        "icon": "mdi:car-tire-alert",
        "device_class": "pressure",
        "state_class": "measurement",
        "unit_of_measurement": "bar",
        "entity_category": "diagnostic"
    },
    "TPMSInformation.FRTPrsDispBar": {
        "name": "Front Right Tire Pressure (Bar)",
        "icon": "mdi:car-tire-alert",
        "device_class": "pressure",
        "state_class": "measurement",
        "unit_of_measurement": "bar",
        "entity_category": "diagnostic"
    },
    "TPMSInformation.RLTPrsDispBar": {
        "name": "Rear Left Tire Pressure (Bar)",
        "icon": "mdi:car-tire-alert",
        "device_class": "pressure", 
        "state_class": "measurement",
        "unit_of_measurement": "bar",
        "entity_category": "diagnostic"
    },
    "TPMSInformation.RRTPrsDispBar": {
        "name": "Rear Right Tire Pressure (Bar)",
        "icon": "mdi:car-tire-alert",
        "device_class": "pressure",
        "state_class": "measurement",
        "unit_of_measurement": "bar",
        "entity_category": "diagnostic"
    },
    "TPMSInformation.TPrsDispDate": {
        "name": "Tire Pressure Measurement Date",
        "icon": "mdi:calendar",
        "device_class": None,
        "entity_category": "diagnostic"
    },
    "TPMSInformation.TPrsDispYear": {
        "name": "Tire Pressure Measurement Year",
        "icon": "mdi:calendar",
        "device_class": None,
        "entity_category": "diagnostic"
    },
    "TPMSInformation.TPrsDispMonth": {
        "name": "Tire Pressure Measurement Month",
        "icon": "mdi:calendar",
        "device_class": None,
        "entity_category": "diagnostic"
    },
    "TPMSInformation.TPrsDispHour": {
        "name": "Tire Pressure Measurement Hour",
        "icon": "mdi:clock",
        "device_class": None,
        "entity_category": "diagnostic"
    },
    "TPMSInformation.TPrsDispMinute": {
        "name": "Tire Pressure Measurement Minute",
        "icon": "mdi:clock",
        "device_class": None,
        "entity_category": "diagnostic"
    },
    "TPMSInformation.FLTyrePressWarn": {
        "name": "Front Left Tire Pressure Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Normal", "Warning", "Low Pressure", "Critical", "System Error"],
        "entity_category": "diagnostic"
    },
    "TPMSInformation.FRTyrePressWarn": {
        "name": "Front Right Tire Pressure Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Normal", "Warning", "Low Pressure", "Critical", "System Error"],
        "entity_category": "diagnostic"
    },
    "TPMSInformation.RLTyrePressWarn": {
        "name": "Rear Left Tire Pressure Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Normal", "Warning", "Low Pressure", "Critical", "System Error"],
        "entity_category": "diagnostic"
    },
    "TPMSInformation.RRTyrePressWarn": {
        "name": "Rear Right Tire Pressure Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Normal", "Warning", "Low Pressure", "Critical", "System Error"],
        "entity_category": "diagnostic"
    },
    
    # Warning indicators
    "WngOilShortage": {
        "name": "Oil Shortage Warning",
        "icon": "mdi:oil-alert",
        "device_class": None,
        "options": ["Off", "On"],
        "entity_category": "diagnostic"
    },
    "WngOilAmountExceed": {
        "name": "Oil Amount Exceed Warning",
        "icon": "mdi:oil-alert",
        "device_class": None,
        "options": ["Off", "On"],
        "entity_category": "diagnostic"
    },
    "WngTyrePressureLow": {
        "name": "Tire Pressure Low Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Off", "On"],
        "entity_category": "diagnostic"
    }
}

# CX-5 Health Report Template
CX5_HEALTH_TEMPLATE = {
    # Base odometer and timestamp data
    "OdoDispValue": {
        "name": "Odometer",
        "icon": "mdi:counter",
        "device_class": None,
        "state_class": "total_increasing",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "OdoDispValueMile": {
        "name": "Odometer (Miles)",
        "icon": "mdi:counter",
        "device_class": None,
        "state_class": "total_increasing",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    "OccurrenceDate": {
        "name": "Health Report Date",
        "icon": "mdi:calendar-clock",
        "device_class": "timestamp",
        "entity_category": "diagnostic"
    },
    
    # Oil information
    "OilMntInformation.RemOilDistK": {
        "name": "Oil Change Distance Remaining",
        "icon": "mdi:oil",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "OilMntInformation.RemOilDistMile": {
        "name": "Oil Change Distance Remaining (Miles)",
        "icon": "mdi:oil",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    
    # Regular maintenance information
    "RegularMntInformation.RemRegDistKm": {
        "name": "Maintenance Distance Remaining",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "RegularMntInformation.RemRegDistMile": {
        "name": "Maintenance Distance Remaining (Miles)",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    "RegularMntInformation.MntSetDistKm": {
        "name": "Maintenance Interval",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "km",
        "entity_category": "diagnostic"
    },
    "RegularMntInformation.MntSetDistMile": {
        "name": "Maintenance Interval (Miles)",
        "icon": "mdi:tools",
        "device_class": None,
        "state_class": "measurement",
        "unit_of_measurement": "mi",
        "entity_category": "diagnostic"
    },
    
    # TPMS Information (CX-5 has simplified tire pressure warnings)
    "TPMSInformation.FLTyrePressWarn": {
        "name": "Front Left Tire Pressure Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Normal", "Warning", "Low Pressure", "Critical", "System Error"],
        "entity_category": "diagnostic"
    },
    "TPMSInformation.FRTyrePressWarn": {
        "name": "Front Right Tire Pressure Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Normal", "Warning", "Low Pressure", "Critical", "System Error"],
        "entity_category": "diagnostic"
    },
    "TPMSInformation.RLTyrePressWarn": {
        "name": "Rear Left Tire Pressure Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Normal", "Warning", "Low Pressure", "Critical", "System Error"],
        "entity_category": "diagnostic"
    },
    "TPMSInformation.RRTyrePressWarn": {
        "name": "Rear Right Tire Pressure Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Normal", "Warning", "Low Pressure", "Critical", "System Error"],
        "entity_category": "diagnostic"
    },
    
    # Warning indicators
    "WngOilShortage": {
        "name": "Oil Shortage Warning",
        "icon": "mdi:oil-alert",
        "device_class": None,
        "options": ["Off", "On"],
        "entity_category": "diagnostic"
    },
    "WngOilAmountExceed": {
        "name": "Oil Amount Exceed Warning",
        "icon": "mdi:oil-alert",
        "device_class": None,
        "options": ["Off", "On"],
        "entity_category": "diagnostic"
    },
    "WngTyrePressureLow": {
        "name": "Tire Pressure Low Warning",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "options": ["Off", "On"],
        "entity_category": "diagnostic"
    }
}

# Map VIN prefixes to health report templates
VIN_MODEL_MAP = {
    VIN_PREFIX_MAZDA3: {
        "template": MAZDA3_HEALTH_TEMPLATE,
        "model_name": "Mazda 3",
        "vehicle_type": "Sedan",
    },
    VIN_PREFIX_CX30: {
        "template": CX30_HEALTH_TEMPLATE,
        "model_name": "CX-30",
        "vehicle_type": "Crossover",
    },
    VIN_PREFIX_CX5: {
        "template": CX5_HEALTH_TEMPLATE,
        "model_name": "CX-5",
        "vehicle_type": "SUV",
        "single_tpms_sensor": True,  # CX-5 has a single TPMS sensor for all tires
    }
}
