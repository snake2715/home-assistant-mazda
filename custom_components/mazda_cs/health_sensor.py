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
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
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
    CX5_HEALTH_TEMPLATE,
    VIN_MODEL_MAP
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
        
        # Tracking created sensors to avoid duplicates
        created_sensors = set()
        
        # Structure the health data properly for processing
        health_reports = {}
        
        # Check if data is already in VIN-keyed format
        if isinstance(health_coordinator.data, dict) and health_coordinator.data and all(len(k) > 10 for k in health_coordinator.data.keys()):
            # Data is already structured by VIN
            health_reports = health_coordinator.data
        else:
            # No health data yet
            health_reports = {}
        
        # Always use vehicle info from the main coordinator to set up sensors
        if coordinator.data:
            # Create structure for all VINs even if they don't have health data yet
            for vehicle in coordinator.data:
                vin = vehicle.get("vin")
                if vin and vin not in health_reports:
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
            "Yes" if health_coordinator.data else "No"
        )
        
        # For each vehicle 
        for vin, health_report in health_reports.items():
            _LOGGER.info("Processing health sensors for vehicle with VIN: %s", vin)
            
            # Try to get vehicle info from the coordinator
            vehicle_info = None
            vehicle_details = ""
            vin_prefix = ""
            
            if vin:
                vin_prefix = vin[:8]  # Extract first 8 characters for model identification
                
            # Get vehicle information
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
            
            # Get the appropriate template based on VIN prefix but always use API vehicle details
            # for display and entity properties to ensure consistency
            template_key = MODEL_TEMPLATE_MAP.get(vin_prefix)
            
            # If no exact match, try partial matching for more robust detection
            if not template_key:
                if any(prefix in vin_prefix for prefix in ["3MZBPA", "JM1BP", "JMBPA"]):
                    template_key = "MAZDA3"
                    _LOGGER.info("Using Mazda 3 template for VIN %s (partial match)", vin)
                elif any(prefix in vin_prefix for prefix in ["3MVDM", "JM1DV", "MM1DV"]):
                    template_key = "CX30"
                    _LOGGER.info("Using CX-30 template for VIN %s (partial match)", vin)
                elif any(prefix in vin_prefix for prefix in ["JM3KF", "JM3KB", "MM3KB"]):
                    template_key = "CX5"
                    _LOGGER.info("Using CX-5 template for VIN %s (partial match)", vin)
            
            # Set template and vehicle model info based on detected model
            template = GENERAL_HEALTH_TEMPLATE
            vehicle_model_info = {}
            
            if template_key == "MAZDA3":
                template = MAZDA3_HEALTH_TEMPLATE
                vehicle_model_info = VIN_MODEL_MAP.get(VIN_PREFIX_MAZDA3, {})
                _LOGGER.info("Using Mazda 3 template for VIN %s", vin)
            elif template_key == "CX30":
                template = CX30_HEALTH_TEMPLATE
                vehicle_model_info = VIN_MODEL_MAP.get(VIN_PREFIX_CX30, {})
                _LOGGER.info("Using CX-30 template for VIN %s", vin)
            elif template_key == "CX5":
                template = CX5_HEALTH_TEMPLATE
                vehicle_model_info = VIN_MODEL_MAP.get(VIN_PREFIX_CX5, {})
                _LOGGER.info("Using CX-5 template for VIN %s", vin)
                
                # Log special handling for CX-5 TPMS
                if vehicle_model_info.get("single_tpms_sensor", False):
                    _LOGGER.info("CX-5 detected: Using single TPMS sensor handling")
            else:
                _LOGGER.info("Using general template for VIN %s (no specific model template found)", vin)
            
            # Enhance vehicle_model_info with API data to ensure consistency
            if vehicle_info:
                # Override template model name with API model name for consistency
                api_model_name = vehicle_info.get("carlineName", "")
                api_model_year = vehicle_info.get("modelYear", "")
                api_model_code = vehicle_info.get("modelCode", "")
                
                if api_model_name:
                    vehicle_model_info["model_name"] = api_model_name
                    _LOGGER.debug("Using API model name '%s' instead of template model name", api_model_name)
                
                # Add extra vehicle info from API that might be useful
                vehicle_model_info["api_data"] = {
                    "model_name": api_model_name,
                    "model_year": api_model_year,
                    "model_code": api_model_code,
                    "nickname": vehicle_info.get("nickname", ""),
                    "exterior_color": vehicle_info.get("exteriorColorName", ""),
                    "interior_color": vehicle_info.get("interiorColorName", ""),
                }
                
                _LOGGER.debug("Enhanced vehicle model info with API data for consistency")
            
            # Process data within remoteInfos if present (new API format)
            report_data = {}
            if health_report:
                if "remoteInfos" in health_report and isinstance(health_report["remoteInfos"], list) and health_report["remoteInfos"]:
                    report_data = health_report["remoteInfos"][0]
                    _LOGGER.info("Found remoteInfos data structure in health report")
                else:
                    # Otherwise use the health report directly
                    report_data = health_report
            
            # Create sensors from template with available data or defaults
            for path, config in template.items():
                # Skip if we've already created this sensor
                sensor_id = f"{vin}_{path}"
                if sensor_id in created_sensors:
                    continue
                
                created_sensors.add(sensor_id)
                
                # Check if we have real data for this path
                value = None
                if report_data:
                    value = get_value_from_path(report_data, path)
                
                # Create the sensor
                name = config.get("name", path.split(".")[-1])
                
                # Determine if timestamp conversion is needed
                is_timestamp = False
                if config.get("device_class") == "timestamp" or any(ts_word in path.lower() for ts_word in ["date", "time", "occurrence"]):
                    is_timestamp = True
                
                entity_category = _convert_entity_category(config.get("entity_category"))
                
                # Create template-based sensor - will use real data when available
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
                    is_timestamp,
                    is_template_only=True,
                    template_default=None,
                    vehicle_info=vehicle_model_info
                )
                entities.append(sensor)
                
                if value is not None:
                    _LOGGER.debug(f"Created sensor '{name}' with initial value: {value}")
                else:
                    _LOGGER.debug(f"Created sensor '{name}' without initial value")
            
            # If discovery mode is enabled, also log all health report paths
            if discovery_mode and health_report:
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
        
        # Add all discovered sensors
        if entities:
            _LOGGER.info("Adding %d health sensors", len(entities))
            async_add_entities(entities)
        else:
            _LOGGER.warning("No health sensors were discovered")
    
    except Exception as e:
        _LOGGER.error("Error setting up Mazda health sensors: %s", e)
        _LOGGER.error(traceback.format_exc())

def get_value_from_path(data, path):
    """Get a value from a nested dictionary using a dot-separated path.
    
    This function handles the complexities of the Mazda API response structure,
    particularly the remoteInfos array and other nested data formats.
    """
    if not data:
        return None
    
    # Handle common API data structures
    processed_data = data
    
    # Handle remoteInfos array which is common in health reports
    if isinstance(processed_data, dict) and "remoteInfos" in processed_data:
        if isinstance(processed_data["remoteInfos"], list) and processed_data["remoteInfos"]:
            processed_data = processed_data["remoteInfos"][0]
            # Log that we're using the first item from remoteInfos
            _LOGGER.debug("Using first item from remoteInfos array for path: %s", path)
    
    # Some health reports wrap data in a "RegularMntInformation" or "TPMSInformation" root
    # If the path starts with one of these prefixes but the data is directly in the dict,
    # we should try to adapt
    top_level_containers = ["RegularMntInformation", "TPMSInformation", "RemoteInfoDriveInformation"]
    path_prefix = path.split(".")[0] if "." in path else path
    
    if (path_prefix in top_level_containers and 
        path_prefix not in processed_data and 
        any(container in processed_data for container in top_level_containers)):
        # The path expects a container, but the data might be directly in the dict or in another container
        # Try all possible containers
        for container in top_level_containers:
            if container in processed_data:
                # Check if the path without the prefix exists in this container
                if "." in path:
                    suffix = path.split(".", 1)[1]
                    temp_value = get_value_from_nested_dict(processed_data[container], suffix)
                    if temp_value is not None:
                        return temp_value
    
    # Try the regular path
    return get_value_from_nested_dict(processed_data, path)

def get_value_from_nested_dict(data, path):
    """Navigate a nested dictionary using dot notation path."""
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
            force_timestamp_conversion=False,
            is_template_only=False,
            template_default=None,
            vehicle_info=None
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
        self._is_template_only = is_template_only
        self._template_default = template_default
        self._vehicle_info = vehicle_info
        
        # Create a unique_id based on VIN and data path
        self._unique_id = f"{DOMAIN}_{vin}_health_{data_path}"
        self._attr_has_entity_name = True
        
        # Set up device info to link this entity to the vehicle device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
        )
        
        # Add extra attributes for more detailed vehicle information display
        if self._vehicle_info and "api_data" in self._vehicle_info:
            api_data = self._vehicle_info["api_data"]
            self._attr_extra_state_attributes = {
                "vin": self._vin,
                "model_name": api_data.get("model_name", ""),
                "model_year": api_data.get("model_year", ""),
                "model_code": api_data.get("model_code", ""),
                "nickname": api_data.get("nickname", ""),
                "exterior_color": api_data.get("exterior_color", ""),
                "interior_color": api_data.get("interior_color", ""),
                "data_path": self._data_path,
                "sensor_type": "health",
            }
        
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
            # For template-only sensors with no data yet, return template default
            if self._is_template_only and (not self.coordinator.data or self._vin not in self.coordinator.data):
                return self._get_template_default_value()
                
            # Try to get actual data from coordinator
            if self.coordinator.data and self._vin in self.coordinator.data:
                value = get_value_from_path(self.coordinator.data[self._vin], self._data_path)
                
                # If we have a real value, process and return it
                if value is not None:
                    return self._process_value(value)
                    
            # Fall back to template default if no data available
            return self._get_template_default_value()
                
        except Exception as ex:
            _LOGGER.debug("Error getting value for %s: %s", self._data_path, ex)
            # Fall back to template default
            return self._get_template_default_value()
            
    def _get_template_default_value(self):
        """Return the appropriate default value based on sensor type."""
        # If a specific default was provided, use it
        if self._template_default is not None:
            return self._template_default
            
        # Otherwise infer a reasonable default based on the sensor type
        if self._device_class == SensorDeviceClass.TIMESTAMP:
            return None
        elif self._options is not None and len(self._options) > 0:
            return self._options[0]  # First option (usually "Off")
        elif self._unit_of_measurement in (UnitOfLength.KILOMETERS, UnitOfLength.MILES):
            return 0
        elif self._unit_of_measurement == PERCENTAGE:
            return 0
        elif self._unit_of_measurement in (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT):
            return None
        elif self._unit_of_measurement in (UnitOfPressure.KPA, UnitOfPressure.PSI):
            return None
        else:
            return None

    def _process_value(self, value):
        """Process the raw value based on sensor type."""
        # Handle options-based sensors (like enums or booleans)
        if self._options and isinstance(value, (int, float)):
            try:
                # Special handling for TPMS warnings in CX-5 vehicles
                if (
                    self._vehicle_info and 
                    self._vehicle_info.get("single_tpms_sensor", False) and
                    "TyrePressWarn" in self._data_path
                ):
                    # For CX-5 with single TPMS sensor, if one of the TPMS paths is requested
                    # (FL, FR, RL, RR), determine the master TPMS value and use it for all
                    tpms_paths = [
                        "TPMSInformation.FLTyrePressWarn",
                        "TPMSInformation.FRTyrePressWarn", 
                        "TPMSInformation.RLTyrePressWarn", 
                        "TPMSInformation.RRTyrePressWarn"
                    ]
                    
                    # Only do this lookup once for performance
                    if self.coordinator.data and self._vin in self.coordinator.data:
                        report_data = self.coordinator.data[self._vin]
                        
                        # Try all TPMS paths to find any value
                        for path in tpms_paths:
                            master_value = get_value_from_path(report_data, path)
                            if master_value is not None:
                                # Use the first found value for all tires
                                _LOGGER.debug(f"CX-5 single TPMS sensor: Using value {master_value} from {path} for all tires")
                                index = min(int(master_value), len(self._options) - 1)
                                return self._options[index]
                
                # Standard processing for options-based sensors
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
                        
                    # Format: "YYYY/MM/DD hh:mm:ss" (common format)
                    elif re.match(r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$', value):
                        dt = datetime.strptime(value, "%Y/%m/%d %H:%M:%S")
                        return dt.replace(tzinfo=timezone.utc)
                        
                    # Format: "YYYY-MM-DD hh:mm:ss" (common format)
                    elif re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', value):
                        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                        return dt.replace(tzinfo=timezone.utc)
                
            except (ValueError, TypeError) as e:
                _LOGGER.warning(f"Failed to convert timestamp value '{value}': {e}")
                # Return original value if conversion fails
                return value
                
        # For numeric values with units, ensure they're properly formatted
        if self._unit_of_measurement:
            try:
                if isinstance(value, str) and value.strip().isdigit():
                    return int(value.strip())
                elif isinstance(value, str) and value.replace('.', '', 1).isdigit():
                    return float(value.strip())
            except (ValueError, TypeError):
                pass
        
        # Return the original value for all other cases
        return value

    @property
    def available(self):
        """Return True if entity is available."""
        # If this is a template-only sensor, it's always available
        if self._is_template_only:
            return True
            
        # Otherwise, check if we have actual data
        if not self.coordinator.data or self._vin not in self.coordinator.data:
            return False
            
        # Check if the specific path has data
        try:
            value = get_value_from_path(self.coordinator.data[self._vin], self._data_path)
            return value is not None
        except Exception:
            return False
            
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "data_path": self._data_path,
            "vin": self._vin
        }
