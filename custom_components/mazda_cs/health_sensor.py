"""Platform for Mazda health report sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
import traceback
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import re

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_CLIENT, 
    DATA_COORDINATOR, 
    DATA_HEALTH_COORDINATOR, 
    DOMAIN, 
    CONF_DISCOVERY_MODE,
    VIN_PREFIX_MAZDA3,
    VIN_PREFIX_CX30,
    VIN_PREFIX_CX5,
    MODEL_TEMPLATE_MAP,
    DEFAULT_TEMPLATE,
    GENERAL_HEALTH_TEMPLATE,
    MAZDA3_HEALTH_TEMPLATE,
    CX30_HEALTH_TEMPLATE,
    CX5_HEALTH_TEMPLATE
)

_LOGGER = logging.getLogger(__name__)

_LOGGER.info("Mazda Health Sensor module loaded")

# Sample test health report - used only to detect possible sensors when no real data is available
SAMPLE_HEALTH_REPORT = {
    "vin123": {
        "battery": {
            "level": 75,
            "health": "good"
        },
        "oil": {
            "life": 50,
            "level": 90
        },
        "tire": {
            "pressure": 35
        },
        "temperature": 22,
        "distance": 50000,
        "date": "2022-01-01",
        "time": "12:00:00"
    }
}

def print_discovery_paths(data, path=None, prefix=''):
    """Print all possible paths in the health report for sensor discovery."""
    if path is None:
        path = []
        
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = path + [key]
            path_str = '.'.join(current_path)
            
            if isinstance(value, (dict, list)):
                # For non-leaf nodes, print path and continue traversing
                _LOGGER.warning(f"{prefix}Path: {path_str} (container)")
                print_discovery_paths(value, current_path, prefix + '  ')
            else:
                # For leaf nodes, print path and value
                value_str = str(value)
                if len(value_str) > 50:
                    value_str = value_str[:47] + "..."
                _LOGGER.warning(f"{prefix}Path: {path_str} = {value_str} ({type(value).__name__})")
    
    elif isinstance(data, list):
        # Handle lists - show example from first item if available
        if data and isinstance(data[0], dict):
            _LOGGER.warning(f"{prefix}Path: {'.'.join(path)} (list of objects, showing first item)")
            print_discovery_paths(data[0], path, prefix + '  ')
        elif data:
            value_str = str(data[0])
            if len(value_str) > 50:
                value_str = value_str[:47] + "..."
            _LOGGER.warning(f"{prefix}Path: {'.'.join(path)}[0] = {value_str} ({type(data[0]).__name__})")

def _convert_entity_category(entity_category_str):
    """Convert entity category string to EntityCategory enum."""
    if entity_category_str == "diagnostic":
        return EntityCategory.DIAGNOSTIC
    elif entity_category_str == "config":
        return EntityCategory.CONFIG
    return None

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Mazda Connected Services health sensors from config entry."""
    try:
        client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
        coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
        health_coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_HEALTH_COORDINATOR]
        
        # Check discovery mode
        discovery_mode = config_entry.options.get(CONF_DISCOVERY_MODE, False)
        
        entities = []
        
        # Structure the health data properly for processing
        health_reports = {}
        
        # If no health report data is available yet (due to deferred initialization),
        # we'll still set up the entities with empty data. They will update when data arrives.
        has_health_data = False
        
        # Check if data is already in VIN-keyed format
        if isinstance(health_coordinator.data, dict) and health_coordinator.data and all(len(k) > 10 for k in health_coordinator.data.keys()):
            # Data is already structured by VIN
            health_reports = health_coordinator.data
            has_health_data = True
        else:
            # No health data yet or data might be a direct API response
            # First, try to use vehicle info from the main coordinator to at least set up entities
            if coordinator.data:
                _LOGGER.info("Health report data not yet available. Setting up sensors with empty data.")
                # Create empty health reports structure based on vehicle VINs
                for vehicle in coordinator.data:
                    vin = vehicle.get("vin")
                    if vin:
                        # Initialize with empty dict - will be populated on next update
                        health_reports[vin] = {}
            else:
                # If we have no vehicle data either, we can't set up health sensors yet
                _LOGGER.warning("No vehicle data available, deferring health sensor setup")
                return
        
        if not health_reports:
            _LOGGER.warning("No health report data yet and no vehicles found")
            return
            
        _LOGGER.info(
            "Setting up health sensors for %d vehicles. Has health data: %s", 
            len(health_reports), 
            has_health_data
        )
        
        # For each vehicle that has a health report
        for vin, health_report in health_reports.items():
            _LOGGER.info("Processing health sensors for vehicle with VIN: %s", vin)
            
            # Try to get vehicle info from the coordinator
            vehicle_info = None
            vehicle_details = ""
            vin_prefix = ""
            if vin:
                vin_prefix = vin[:8]  # Extract first 8 characters for model identification
                
            if coordinator.data:
                for vehicle in coordinator.data:
                    if vehicle.get("vin") == vin:
                        vehicle_info = vehicle
                        
                        # Get vehicle details for logging
                        nickname = vehicle.get("nickname", "")
                        model_name = vehicle.get("carlineName", "Unknown")
                        year = vehicle.get("modelYear", "")
                        
                        # Get car type info
                        car_type = vehicle.get("carType", "").capitalize()
                        if not car_type:
                            if "cx" in model_name.lower():
                                car_type = "SUV/Crossover"
                            elif "mx" in model_name.lower():
                                car_type = "Roadster"
                            else:
                                car_type = "Sedan"
                        
                        vehicle_details = f"{nickname} " if nickname else ""
                        vehicle_details += f"({year} {model_name} - {car_type})"
                        
                        _LOGGER.info("Found vehicle details: %s", vehicle_details)
                        break
            
            if has_health_data and health_report:
                # Log the full health report structure at debug level to help with troubleshooting
                if vehicle_details:
                    _LOGGER.debug(
                        "Full health report structure for %s: %s", 
                        vehicle_details,
                        json.dumps(health_report, indent=2, default=str)
                    )
                else:
                    _LOGGER.debug(
                        "Full health report structure for VIN %s: %s", 
                        vin,
                        json.dumps(health_report, indent=2, default=str)
                    )
            
            # Discover sensors from the health report
            sensors = []
            try:
                if has_health_data and health_report:
                    if discovery_mode:
                        # Log which car model has which sensors for easier templating
                        if vehicle_details:
                            _LOGGER.warning(
                                "DISCOVERY MODE - Sensor paths for vehicle model: %s", 
                                vehicle_details
                            )
                        else:
                            _LOGGER.warning(
                                "DISCOVERY MODE - Sensor paths for VIN: %s", 
                                vin
                            )
                        print_discovery_paths(health_report)
                        
                    # Get the appropriate template based on VIN prefix
                    template_key = None
                    template = None
                    
                    # Try to determine which template to use based on VIN prefix
                    if vin_prefix:
                        template_key = MODEL_TEMPLATE_MAP.get(vin_prefix)
                        
                        if template_key == "MAZDA3":
                            template = MAZDA3_HEALTH_TEMPLATE
                            _LOGGER.info("Using Mazda 3 template for VIN %s", vin)
                        elif template_key == "CX30":
                            template = CX30_HEALTH_TEMPLATE
                            _LOGGER.info("Using CX-30 template for VIN %s", vin)
                        elif template_key == "CX5":
                            template = CX5_HEALTH_TEMPLATE
                            _LOGGER.info("Using CX-5 template for VIN %s", vin)
                    
                    # If no specific template found, use general template
                    if not template:
                        template = GENERAL_HEALTH_TEMPLATE
                        _LOGGER.info("Using general template for VIN %s (no specific model template found)", vin)
                    
                    # Process data within remoteInfos if present (new API format)
                    if "remoteInfos" in health_report and isinstance(health_report["remoteInfos"], list) and health_report["remoteInfos"]:
                        report_data = health_report["remoteInfos"][0]
                        _LOGGER.info("Found remoteInfos data structure in health report")
                    else:
                        # Otherwise use the health report directly (may be pre-processed)
                        report_data = health_report
                    
                    # Create sensors based on the template and available data
                    for path, config in template.items():
                        # Extract value using the path from template
                        value = get_value_from_path(report_data, path)
                        
                        if value is not None or discovery_mode:
                            # Create sensor with the extracted value
                            name = config.get("name", path.split(".")[-1])
                            
                            # Determine if timestamp conversion is needed
                            is_timestamp = False
                            if config.get("device_class") == "timestamp" or any(ts_word in path.lower() for ts_word in ["date", "time", "occurrence"]):
                                is_timestamp = True
                            
                            entity_category = _convert_entity_category(config.get("entity_category"))
                            
                            sensor = MazdaHealthSensor(
                                health_coordinator,
                                vin,
                                path,  # Use path as unique identifier
                                name,
                                config.get("icon"),
                                config.get("device_class"),
                                config.get("state_class"),
                                config.get("unit_of_measurement"),
                                entity_category,
                                config.get("options"),
                                is_timestamp
                            )
                            sensors.append(sensor)
                            
                            if value is not None:
                                _LOGGER.info(f"Created sensor '{name}' with value: {value}")
                            else:
                                _LOGGER.info(f"Created sensor '{name}' with no value yet")
                
                elif discovery_mode:
                    # In discovery mode, create all sensors from all templates for testing
                    _LOGGER.warning("DISCOVERY MODE - Creating all possible sensors for testing")
                    
                    # Combine all templates for testing
                    combined_template = {}
                    combined_template.update(GENERAL_HEALTH_TEMPLATE)
                    combined_template.update(MAZDA3_HEALTH_TEMPLATE)
                    combined_template.update(CX30_HEALTH_TEMPLATE)
                    combined_template.update(CX5_HEALTH_TEMPLATE)
                    
                    for path, config in combined_template.items():
                        name = config.get("name", path.split(".")[-1])
                        
                        # Determine if timestamp conversion is needed
                        is_timestamp = False
                        if config.get("device_class") == "timestamp" or any(ts_word in path.lower() for ts_word in ["date", "time", "occurrence"]):
                            is_timestamp = True
                        
                        entity_category = _convert_entity_category(config.get("entity_category"))
                        
                        sensor = MazdaHealthSensor(
                            health_coordinator,
                            vin,
                            path,  # Use path as unique identifier
                            name,
                            config.get("icon"),
                            config.get("device_class"),
                            config.get("state_class"),
                            config.get("unit_of_measurement"),
                            entity_category,
                            config.get("options"),
                            is_timestamp
                        )
                        sensors.append(sensor)
                
                else:
                    _LOGGER.warning("No health report data available for VIN %s", vin)
            
            except Exception as e:
                _LOGGER.error("Error processing health sensors for vehicle %s: %s", vin, e)
                _LOGGER.error(traceback.format_exc())
        
        # Add all discovered sensors
        if sensors:
            async_add_entities(sensors)
        else:
            _LOGGER.warning("No health sensors were discovered")
    
    except Exception as e:
        _LOGGER.error("Error setting up Mazda health sensors: %s", e)
        _LOGGER.error(traceback.format_exc())

def get_value_from_path(data, path):
    """Get a value from a nested dictionary using a dot-separated path."""
    if not data:
        return None
    
    parts = path.split(".")
    current = data
    
    try:
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current
    except (KeyError, TypeError):
        return None

class MazdaHealthSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Mazda health sensor."""

    def __init__(
        self,
        coordinator,
        vin,
        data_path,
        name,
        icon,
        device_class,
        state_class,
        unit_of_measurement,
        entity_category,
        options=None,
        force_timestamp_conversion=False
    ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._vin = vin
        self._data_path = data_path
        self._name = name
        self._icon = icon
        self._device_class = device_class
        self._state_class = state_class
        self._unit_of_measurement = unit_of_measurement
        self._entity_category = entity_category
        self._options = options
        self._force_timestamp_conversion = force_timestamp_conversion
        
        # Create a unique_id based on VIN and data path
        self._unique_id = f"{DOMAIN}_{vin}_health_{data_path}"
        self._attr_has_entity_name = True
        
        # Debug log for init
        _LOGGER.debug(
            "Initialized health sensor %s for VIN %s with path %s",
            name, vin, data_path
        )

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Return the icon of the sensor."""
        return self._icon

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        return self._state_class

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement

    @property
    def entity_category(self):
        """Return the entity category."""
        return self._entity_category

    @property
    def native_value(self):
        """Return the state of the sensor."""
        try:
            if not self.coordinator.data:
                return None
                
            # Find data for this VIN
            if self._vin not in self.coordinator.data:
                return None
                
            report = self.coordinator.data.get(self._vin, {})
            
            # Process data within remoteInfos if present (new API format)
            if "remoteInfos" in report and isinstance(report["remoteInfos"], list) and report["remoteInfos"]:
                data = report["remoteInfos"][0]
            else:
                # Otherwise use the report directly (may be pre-processed)
                data = report
            
            # Extract value using the path
            value = get_value_from_path(data, self._data_path)
            
            # Process the value based on sensor type
            if value is None:
                return None
                
            # Handle options-based sensors (like enums or booleans)
            if self._options and isinstance(value, (int, float)):
                # Typically 0 is "Off" and anything else is "On" or other state
                try:
                    index = min(int(value), len(self._options) - 1)
                    return self._options[index]
                except (ValueError, TypeError, IndexError):
                    return str(value)
            
            # Handle timestamp values
            if self._force_timestamp_conversion or (
                self._device_class == SensorDeviceClass.TIMESTAMP or
                any(marker in self._data_path.lower() for marker in ["date", "time", "occurrence"])
            ):
                try:
                    # Try different timestamp formats
                    if isinstance(value, str):
                        # Format: "YYYYMMDDhhmmss" (e.g. "20250228041016")
                        if re.match(r'^\d{14}$', value):
                            dt = datetime.strptime(value, "%Y%m%d%H%M%S")
                            return dt.replace(tzinfo=timezone.utc)
                            
                        # Format: "YYYY-MM-DD'T'hh:mm:ss'Z'" (ISO format)
                        elif "T" in value and (value.endswith("Z") or "+" in value):
                            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                            return dt
                            
                        # Other potential formats can be added here
                        
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Failed to convert timestamp value '{value}': {e}")
                    # Return original value if conversion fails
                    return value
            
            return value
            
        except Exception as e:
            _LOGGER.error("Error getting value for sensor %s: %s", self._name, str(e))
            return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "data_path": self._data_path,
            "vin": self._vin
        }

    @property
    def available(self):
        """Return True if entity is available."""
        # Check if coordinator is available and has data for this VIN
        if not self.coordinator.last_update_success:
            return False
            
        if not self.coordinator.data:
            return False
            
        if self._vin not in self.coordinator.data:
            return False
            
        return True
