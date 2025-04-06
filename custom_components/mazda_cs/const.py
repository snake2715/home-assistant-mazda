"""Constants for the Mazda Connected Services integration."""

DOMAIN = "mazda_cs"

DATA_CLIENT = "mazda_client"
DATA_COORDINATOR = "coordinator"
DATA_HEALTH_COORDINATOR = "health_coordinator"
DATA_REGION = "region"
DATA_VEHICLES = "vehicles"

MAZDA_REGIONS = {"MNAO": "North America", "MME": "Europe", "MJO": "Japan"}

# VIN Prefixes for identifying Mazda models
VIN_PREFIX_CX5 = "JM3KFBBL"  # Mazda CX-5 VIN prefix
VIN_PREFIX_CX30 = "3MVDMBBM"  # Mazda CX-30 VIN prefix  
VIN_PREFIX_MAZDA3 = "3MZBPABM"  # Mazda 3 VIN prefix

# Map of VIN prefixes to model templates
MODEL_TEMPLATE_MAP = {
    VIN_PREFIX_MAZDA3: "MAZDA3",
    VIN_PREFIX_CX30: "CX30",
    VIN_PREFIX_CX5: "CX5",
}

# Default fallback template if no matching template is found
DEFAULT_TEMPLATE = "GENERAL"

# General template with common sensors that should work across all models
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
    
    # TPMS information - CX-5 specific
    "TPMSInformation.TPMSStatus": {
        "name": "Tire Pressure Status",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "entity_category": "diagnostic",
        "value_map": {
            "0": "Normal",
            "1": "Warning",
            "2": "Low Pressure",
            "3": "Critical",
            "4": "System Error"
        }
    },
    "TPMSInformation.TPMSSystemFlt": {
        "name": "TPMS System Status",
        "icon": "mdi:car-tire-alert",
        "device_class": None,
        "entity_category": "diagnostic",
        "value_map": {
            "0": "Normal",
            "1": "Fault"
        }
    }
    # Removed individual tire pressure sensors for CX-5 since it uses a single TPMS sensor
}