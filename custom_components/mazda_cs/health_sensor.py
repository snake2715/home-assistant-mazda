"""Platform for Mazda health report sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
import traceback
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

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

from .const import DATA_CLIENT, DATA_COORDINATOR, DATA_HEALTH_COORDINATOR, DOMAIN

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

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Mazda Connected Services health sensors from config entry."""
    try:
        _LOGGER.info("Setting up Mazda health sensors")
        
        # Check if health coordinator exists
        if DATA_HEALTH_COORDINATOR not in hass.data[DOMAIN][config_entry.entry_id]:
            _LOGGER.error("Health coordinator not found in hass.data for entry %s", config_entry.entry_id)
            return
            
        health_coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_HEALTH_COORDINATOR]
        
        _LOGGER.info("Health coordinator data: %s", 
                     "Available" if health_coordinator.data else "Not available")
        
        # If we don't have data yet, try to use the coordinator's last_successful_reports instead
        if not health_coordinator.data:
            _LOGGER.warning("No health report data available in coordinator, checking cached data")
            if hasattr(health_coordinator, 'last_successful_reports') and health_coordinator.last_successful_reports:
                _LOGGER.info("Using cached last successful reports: %s vehicles", 
                            len(health_coordinator.last_successful_reports))
                health_coordinator.data = health_coordinator.last_successful_reports
            else:
                _LOGGER.warning("No health report data available for entry %s", config_entry.entry_id)
                # Use sample data for testing entity setup
                _LOGGER.info("Using sample health report for entity discovery")
                # Get VIN from config entry
                vin = config_entry.data.get("vehicle_id")
                if vin:
                    health_coordinator.data = {vin: SAMPLE_HEALTH_REPORT[list(SAMPLE_HEALTH_REPORT.keys())[0]]}
                else:
                    return
        
        _LOGGER.debug("Health coordinator data keys: %s", 
                     list(health_coordinator.data.keys()) if isinstance(health_coordinator.data, dict) else "Not a dict")
        
        entities = []
        
        # Structure the health data properly for processing
        health_reports = {}
        
        # Check if data is already in VIN-keyed format
        if isinstance(health_coordinator.data, dict) and all(len(k) > 10 for k in health_coordinator.data.keys()):
            # Data is already structured by VIN
            health_reports = health_coordinator.data
        else:
            # Data might be a direct API response, check if it's a raw health report
            if isinstance(health_coordinator.data, dict):
                # Get VIN from config entry
                vin = config_entry.data.get("vehicle_id")
                if not vin:
                    _LOGGER.warning("No vehicle ID found in config entry, cannot process health report")
                    return
                    
                _LOGGER.debug("Using vehicle_id %s from config entry for health report", vin)
                health_reports = {vin: health_coordinator.data}
        
        _LOGGER.info("Processing health reports for %d vehicles", len(health_reports))
        
        # For each vehicle that has a health report
        for vin, health_report in health_reports.items():
            _LOGGER.info("Processing health report for vehicle with VIN: %s", vin)
            
            # Log the full health report structure at debug level to help with troubleshooting
            _LOGGER.debug(
                "Full health report structure for VIN %s: %s", 
                vin,
                json.dumps(health_report, indent=2, default=str)
            )
            
            # Discover sensors from the health report
            sensors = []
            try:
                sensors = discover_health_sensors(health_report)
                
                _LOGGER.info(
                    "Discovered %d health sensors for vehicle %s", 
                    len(sensors), 
                    vin
                )
                
                # Log the discovered sensors at debug level
                for sensor in sensors:
                    _LOGGER.debug(
                        "Discovered health sensor: %s (key: %s, path: %s, unit: %s)", 
                        sensor.name, 
                        sensor.key, 
                        sensor.path, 
                        sensor.native_unit_of_measurement
                    )
                    
            except Exception as ex:
                _LOGGER.exception("Error discovering health sensors for VIN %s: %s", vin, ex)
                _LOGGER.error(traceback.format_exc())
            
            # Create entities for each sensor
            for sensor_description in sensors:
                try:
                    entity = MazdaHealthSensor(
                        health_coordinator,
                        sensor_description,
                        vin,
                    )
                    entities.append(entity)
                except Exception as ex:
                    _LOGGER.error("Error creating sensor entity for %s with path %s: %s",
                                 sensor_description.name, sensor_description.path, ex)
                    _LOGGER.debug(traceback.format_exc())
        
        if not entities:
            _LOGGER.warning("No health sensors discovered for any vehicle")
            return
            
        _LOGGER.info("Adding %d health sensor entities", len(entities))
        async_add_entities(entities)
        
    except Exception as ex:
        _LOGGER.error("Error setting up Mazda health sensors: %s", ex)
        _LOGGER.error(traceback.format_exc())


@dataclass
class MazdaHealthSensorEntityDescription(SensorEntityDescription):
    """Describes a Mazda health report sensor entity."""

    path: List[str] = None
    transform_value: Optional[Callable[[Any], StateType]] = None


def discover_health_sensors(health_report):
    """Discover health report sensors in the nested structure."""
    if not health_report:
        _LOGGER.warning("Empty health report, no sensors to discover")
        return []
    
    _LOGGER.debug("Health report top-level keys: %s", list(health_report.keys()))
    
    sensors = []
    
    # Check for common API response formats and process accordingly
    if "remoteInfos" in health_report and isinstance(health_report["remoteInfos"], list):
        _LOGGER.info("Found remoteInfos array in health report with %d items", 
                     len(health_report["remoteInfos"]))
        
        # Process remoteInfos array
        for item in health_report["remoteInfos"]:
            traverse_dict(item, ["remoteInfos"], sensors)
        
        # Also process the parent object for any fields we missed
        for key, value in health_report.items():
            if key != "remoteInfos":
                traverse_dict({key: value}, [], sensors)
                
    # Check for resultItems array structure (alternative Mazda API response format)
    elif "resultItems" in health_report and isinstance(health_report["resultItems"], list):
        _LOGGER.info("Found resultItems array in health report with %d items", 
                     len(health_report["resultItems"]))
        
        # Process resultItems array
        for item in health_report["resultItems"]:
            traverse_dict(item, ["resultItems"], sensors)
            
        # Also process the parent object for any fields we missed
        for key, value in health_report.items():
            if key != "resultItems":
                traverse_dict({key: value}, [], sensors)
                
    # Check for common structures in health report
    elif any(key in health_report for key in ["TPMSInformation", "OilMntInformation", "RegularMntInformation"]):
        _LOGGER.info("Found typical health report structure")
        traverse_dict(health_report, [], sensors)
        
    # Check for result structure
    elif "result" in health_report and isinstance(health_report["result"], dict):
        _LOGGER.info("Found result dictionary in health report")
        traverse_dict(health_report["result"], ["result"], sensors)
        
        # Also process the parent object for any fields we missed
        for key, value in health_report.items():
            if key != "result":
                traverse_dict({key: value}, [], sensors)
                
    # Fallback for other formats - try to process everything
    else:
        _LOGGER.info("Processing health report as general dictionary")
        traverse_dict(health_report, [], sensors)
    
    # Deduplicate sensors based on path
    seen_paths = set()
    unique_sensors = []
    
    for sensor in sensors:
        path_key = str(sensor.path)
        if path_key not in seen_paths:
            seen_paths.add(path_key)
            unique_sensors.append(sensor)
    
    # Log summary of discovered sensors
    sensor_types = {}
    sensor_names = [s.name for s in unique_sensors]
    
    for s in unique_sensors:
        device_class = s.device_class or "generic"
        if device_class in sensor_types:
            sensor_types[device_class] += 1
        else:
            sensor_types[device_class] = 1
    
    _LOGGER.info("Discovered %d total sensors with types: %s", len(unique_sensors), dict(sensor_types))
    _LOGGER.debug("Discovered sensor names: %s", sensor_names)
    
    return unique_sensors


def traverse_dict(data, path, sensors):
    """Traverse the health report dictionary and discover sensors."""
    if not data:
        return
        
    _LOGGER.debug("Traversing path: %s, Data type: %s", path, type(data))
    
    # Handle different data types appropriately
    if isinstance(data, dict):
        # Structure 1: remoteInfos array format from the API
        if "remoteInfos" in data and isinstance(data["remoteInfos"], list):
            _LOGGER.debug("Found remoteInfos array at path %s", path)
            for item in data["remoteInfos"]:
                traverse_dict(item, path + ["remoteInfos"], sensors)
            
            # Also process other keys at this level
            for key, value in data.items():
                if key != "remoteInfos":
                    traverse_dict({key: value}, path, sensors)
            return
            
        # Structure 2: resultItems array format from the API
        if "resultItems" in data and isinstance(data["resultItems"], list):
            _LOGGER.debug("Found resultItems array at path %s", path)
            for item in data["resultItems"]:
                traverse_dict(item, path + ["resultItems"], sensors)
                
            # Also process other keys at this level
            for key, value in data.items():
                if key != "resultItems":
                    traverse_dict({key: value}, path, sensors)
            return
        
        # Structure 3: Handle items with name/value pairs (common API format)
        if "name" in data and "value" in data:
            try:
                name = data["name"]
                value = data["value"]
                units = data.get("unit", "")
                
                _LOGGER.debug("Found name/value pair: %s=%s%s", name, value, units)
                
                # Skip certain values that might not be useful as sensors
                if name in ["id", "status", "timestamp"] or value == "":
                    _LOGGER.debug("Skipping %s with value %s - not a useful sensor value", name, value)
                    return
                
                # Create a sensor ID from the path and name
                sensor_id = f"health_{'_'.join(str(p) for p in path)}_{name}".lower() if path else f"health_{name}".lower()
                
                sensors.append(
                    MazdaHealthSensorEntityDescription(
                        key=sensor_id,
                        name=name.replace("_", " ").title(),
                        path=path + [name],
                        native_unit_of_measurement=units,
                    )
                )
                return
            except Exception as ex:
                _LOGGER.warning("Error creating sensor from %s: %s", data, ex)
                _LOGGER.debug(traceback.format_exc())
                return
        
        # Special handling for TPMSInformation, OilMntInformation, and other known structures
        special_sections = ["TPMSInformation", "OilMntInformation", "RegularMntInformation"]
        has_special_section = False
        
        for section in special_sections:
            if section in data and isinstance(data[section], dict):
                has_special_section = True
                new_path = path + [section]
                _LOGGER.debug("Found special section %s, processing with path %s", section, new_path)
                traverse_dict(data[section], new_path, sensors)
        
        # Check for warning keys (starting with "Wng")
        wng_keys = [k for k in data.keys() if isinstance(k, str) and k.startswith("Wng")]
        if wng_keys:
            for wng_key in wng_keys:
                value = data[wng_key]
                if isinstance(value, (int, bool, float)) and wng_key not in ["WngTpmsStatus"]:
                    # Create warning sensor
                    sensor = create_sensor_description(path + [wng_key], value)
                    if sensor:
                        sensors.append(sensor)
            
        # If we processed special sections, don't process other top-level items to avoid duplication
        if has_special_section and any(k in data for k in ["TPMSInformation", "OilMntInformation", "OdoDispValue"]):
            # Still process some important top-level keys
            for key in ["OdoDispValue", "OdoDispValueMile", "OccurrenceDate"]:
                if key in data:
                    sensor = create_sensor_description(path + [key], data[key])
                    if sensor:
                        sensors.append(sensor)
                    
            # Then skip further processing to avoid duplication
            return
        
        # Structure 4: Regular nested dictionary
        for key, value in data.items():
            # Skip if null
            if value is None:
                continue
                
            new_path = path + [key]
            
            if isinstance(value, (dict, list)):
                # Recurse into nested structures
                traverse_dict(value, new_path, sensors)
            elif isinstance(value, (int, float, str, bool)) and value != "":
                # Found a leaf node with a value, create a sensor for it
                _LOGGER.debug("Found leaf node with value at path: %s = %s", new_path, value)
                sensor = create_sensor_description(new_path, value)
                if sensor:
                    sensors.append(sensor)
    
    # Handle list of items
    elif isinstance(data, list):
        _LOGGER.debug("Processing list with %d items at path %s", len(data), path)
        
        # For each item in the list
        for i, item in enumerate(data):
            if isinstance(item, dict):
                # For dictionaries within lists, just add the item index to the path for clarity
                item_path = path + [f"item{i}"]
                traverse_dict(item, item_path, sensors)
            elif isinstance(item, list):
                # For nested lists, also add the item index
                item_path = path + [f"item{i}"]
                traverse_dict(item, item_path, sensors)
            elif isinstance(item, (int, float, str, bool)) and item != "":
                # For primitive values in a list, create a sensor with the list index
                item_path = path + [f"item{i}"]
                sensor = create_sensor_description(item_path, item)
                if sensor:
                    sensors.append(sensor)


def create_sensor_description(path, value):
    """Create a sensor description from a leaf node value."""
    # Skip empty values
    if value == "" or value is None:
        return None
    
    # Ensure all path components are strings for joining
    path_parts = [str(p) for p in path]
    
    # Join the path to create a key and name
    key = f"health_{'_'.join(path_parts)}".lower()
    
    # Use the last path segment as the name
    if path_parts:
        name = path_parts[-1].replace("_", " ").title()
        # If name starts with "item", use the parent path element + index
        if name.startswith("Item") and len(path_parts) > 1:
            parent_name = path_parts[-2].replace("_", " ").title()
            name = f"{parent_name} {name}"
    else:
        name = "Unknown"
    
    _LOGGER.debug("Creating sensor from path %s with value %s", path, value)
    
    # Default description with no special handling
    description = MazdaHealthSensorEntityDescription(
        key=key,
        name=name,
        path=path,
    )
    
    # Special handling based on path and value
    last_segment = path_parts[-1] if path_parts else ""
    
    # Log details about the value type and key being processed
    _LOGGER.debug(
        "Processing value: %s (type: %s) with key: %s, last_segment: %s", 
        value, 
        type(value).__name__, 
        key, 
        last_segment
    )

    # Determine icon, device class, unit, etc. based on key and value type
    icon = "mdi:car-wrench"
    device_class = None
    state_class = None
    entity_category = EntityCategory.DIAGNOSTIC
    unit = None
    
    # Try to infer the appropriate properties based on the key names and value
    path_str = "_".join(path_parts).lower()
    
    # Check for timestamp fields
    if (("date" in path_str.lower() or "time" in path_str.lower() or 
         "timestamp" in path_str.lower() or "occurrence" in path_str.lower()) and 
        isinstance(value, str)):
        
        # Check for format: YYYYMMDDHHMMSS
        if len(value) == 14 and value.isdigit():
            device_class = SensorDeviceClass.TIMESTAMP
            icon = "mdi:clock"
        
        # Check for ISO format with T and colons
        elif "T" in value and ":" in value:
            device_class = SensorDeviceClass.TIMESTAMP
            icon = "mdi:clock"
    
    # Handle TPMS information (tire pressure)
    if "tpmsinformation" in path_str:
        icon = "mdi:tire"
        if "tprs" in path_str and "psi" in path_str:
            device_class = SensorDeviceClass.PRESSURE
            unit = UnitOfPressure.PSI
            name = name.replace("Tprs", "Tire Pressure").replace("Disp", "")
        elif "tprs" in path_str and "bar" in path_str:
            device_class = SensorDeviceClass.PRESSURE
            unit = UnitOfPressure.BAR
            name = name.replace("Tprs", "Tire Pressure").replace("Disp", "")
        elif "tprs" in path_str and "kp" in path_str:
            device_class = SensorDeviceClass.PRESSURE
            unit = UnitOfPressure.KPA
            name = name.replace("Tprs", "Tire Pressure").replace("Disp", "")
        elif "tyrepresswarn" in path_str:
            name = name.replace("Tyre Press Warn", "Tire Pressure Warning")
    
    # Handle oil maintenance information
    elif "oilmntinformation" in path_str:
        icon = "mdi:oil"
        if "remoildist" in path_str:
            device_class = SensorDeviceClass.DISTANCE
            if "mile" in path_str.lower():
                unit = UnitOfLength.MILES
                name = "Oil Change Distance Remaining (Miles)"
            else:
                unit = UnitOfLength.KILOMETERS
                name = "Oil Change Distance Remaining (km)"
    
    # Handle regular maintenance information
    elif "regularmntinformation" in path_str:
        icon = "mdi:wrench"
        if "remregdist" in path_str:
            device_class = SensorDeviceClass.DISTANCE
            if "mile" in path_str.lower():
                unit = UnitOfLength.MILES
                name = "Maintenance Distance Remaining (Miles)"
            else:
                unit = UnitOfLength.KILOMETERS
                name = "Maintenance Distance Remaining (km)"
    
    # Handle odometer
    elif "ododispvalue" in path_str:
        device_class = SensorDeviceClass.DISTANCE
        state_class = SensorStateClass.TOTAL_INCREASING
        if "mile" in path_str.lower():
            unit = UnitOfLength.MILES
            name = "Odometer (Miles)"
        else:
            unit = UnitOfLength.KILOMETERS
            name = "Odometer (km)"
        icon = "mdi:counter"
    
    # Handle warning indicators
    elif path_str.startswith("wng"):
        icon = "mdi:alert-circle-outline"
        name = name.replace("Wng", "Warning ")
    
    # Handle occurrence date (timestamp of report)
    elif "occurrencedate" in path_str:
        device_class = SensorDeviceClass.TIMESTAMP
        icon = "mdi:calendar-clock"
        name = "Last Report Time"
    
    # Generic handling for other types
    elif "battery" in path_str:
        if any(term in path_str for term in ["level", "charge", "percent"]):
            device_class = SensorDeviceClass.BATTERY
            unit = PERCENTAGE
            icon = "mdi:battery"
        elif any(term in path_str for term in ["health", "status"]):
            icon = "mdi:battery-heart-variant"
    
    elif "oil" in path_str:
        icon = "mdi:oil"
        if any(term in path_str for term in ["life", "level", "percent"]):
            unit = PERCENTAGE
    
    elif "tire" in path_str or "tyre" in path_str:
        icon = "mdi:tire"
        if "pressure" in path_str:
            device_class = SensorDeviceClass.PRESSURE
            # Try to determine if it's PSI or kPa based on the value
            if isinstance(value, (int, float)) and value < 100:
                unit = UnitOfPressure.PSI
            else:
                unit = UnitOfPressure.KPA
    
    elif "temperature" in path_str:
        device_class = SensorDeviceClass.TEMPERATURE
        unit = UnitOfTemperature.CELSIUS
        icon = "mdi:thermometer"
    
    elif any(distance_term in path_str for distance_term in ["distance", "mileage", "odometer"]):
        device_class = SensorDeviceClass.DISTANCE
        unit = UnitOfLength.KILOMETERS
        icon = "mdi:counter"
    
    elif any(date_term in path_str for date_term in ["date", "time", "last_update"]):
        device_class = SensorDeviceClass.TIMESTAMP
        icon = "mdi:calendar-clock"
    
    # Handle different value types
    if isinstance(value, bool):
        # For boolean values, don't use a unit
        icon = "mdi:check-circle" if value else "mdi:alert-circle"
    elif isinstance(value, (int, float)):
        # Numeric values might represent measurements
        state_class = SensorStateClass.MEASUREMENT
    
    description.icon = icon
    description.device_class = device_class
    description.state_class = state_class
    description.native_unit_of_measurement = unit
    description.entity_category = entity_category
    description.name = name
    
    return description


def search_health_report(data, search_path):
    """Search for a specific path in a health report dictionary."""
    if not data or not search_path:
        return None
        
    # Clone the search path to avoid modifying the original
    path = search_path.copy()
    
    # Start with the entire data structure
    current = data
    
    try:
        # Convert path for logging
        path_str = ".".join(str(p) for p in search_path)
        _LOGGER.debug("Searching for path: %s in data", path_str)
        
        # Walk through the path segments
        while path and current is not None:
            segment = path.pop(0)
            
            # Handle segment as string
            segment_str = str(segment)
            
            # If current is a dictionary
            if isinstance(current, dict):
                if segment_str in current:
                    current = current[segment_str]
                else:
                    # Key not found
                    _LOGGER.debug("Key %s not found in data at path %s", 
                                segment_str, [str(p) for p in search_path[:-len(path) - 1]])
                    return None
            
            # If current is a list
            elif isinstance(current, list):
                # Try to use segment as an index if possible
                if segment_str.startswith("item") and segment_str[4:].isdigit():
                    idx = int(segment_str[4:])
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        # Index out of range
                        _LOGGER.debug("Index %d out of range in list of length %d", idx, len(current))
                        return None
                elif segment_str.isdigit():
                    # Direct numeric index
                    idx = int(segment_str)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        # Index out of range
                        _LOGGER.debug("Index %d out of range in list of length %d", idx, len(current))
                        return None
                else:
                    # Try to find an item in the list that matches
                    found = False
                    for item in current:
                        if isinstance(item, dict) and segment_str in item:
                            current = item[segment_str]
                            found = True
                            break
                    
                    if not found:
                        _LOGGER.debug("Could not find item %s in list", segment_str)
                        return None
            else:
                # Current is a primitive value but we have more path segments
                _LOGGER.debug("Cannot traverse further - reached primitive value %s at path %s", 
                            current, [str(p) for p in search_path[:-len(path) - 1]])
                return None
                
        # Return the final value
        return current
        
    except Exception as ex:
        _LOGGER.debug("Error searching for path %s in health report: %s", path_str, ex)
        return None


class MazdaHealthSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Mazda health sensor."""

    entity_description: MazdaHealthSensorEntityDescription

    def __init__(
        self,
        coordinator,
        description: MazdaHealthSensorEntityDescription,
        vin: str,
    ) -> None:
        """Initialize the sensor with a coordinator and sensor description."""
        super().__init__(coordinator)
        self.entity_description = description
        self.vin = vin
        
        # Generate unique sensor ID with proper domain prefix
        self._attr_unique_id = f"{DOMAIN}_{vin}_health_{description.key}"
        
        # Set the name based on the description
        self._attr_name = f"{description.name}"
        
        # Create basic device info first
        self._attr_device_info = {
            "identifiers": {(DOMAIN, vin)},
            "manufacturer": "Mazda",
            "model": "Unknown",
            "name": f"Mazda Vehicle ({vin[-6:]})",  # Use last 6 digits of VIN as identifier
            "sw_version": "",
        }
        
        # Find vehicle info from the coordinator if available
        vehicle_info = None
        
        # Try to get vehicle info from coordinator data
        if coordinator.hass:
            try:
                # Get main coordinator if available for vehicle info
                main_coordinator = None
                for entry_id, data in coordinator.hass.data[DOMAIN].items():
                    if DATA_COORDINATOR in data:
                        main_coordinator = data[DATA_COORDINATOR]
                        break
                
                # Try to get vehicle info from main coordinator
                if main_coordinator and main_coordinator.data:
                    for vehicle in main_coordinator.data:
                        if vehicle.get("vin") == vin:
                            vehicle_info = vehicle
                            break
            except (KeyError, AttributeError, TypeError) as err:
                _LOGGER.debug("Could not get vehicle info: %s", err)
        
        # If we found vehicle info, enhance the device info
        if vehicle_info:
            model_name = vehicle_info.get("carlineName", "Unknown")
            year = vehicle_info.get("modelYear", "")
            nickname = vehicle_info.get("nickname", "")
            
            # Use nickname if available, otherwise use year + model
            if nickname:
                vehicle_name = nickname
            else:
                vehicle_name = f"{year} {model_name}".strip()
                if not vehicle_name:
                    vehicle_name = f"Mazda Vehicle ({vin[-6:]})"
            
            self._attr_device_info.update({
                "manufacturer": vehicle_info.get("brand", "Mazda"),
                "model": model_name,
                "name": vehicle_name,
                "sw_version": vehicle_info.get("version", ""),
            })
            
        # Set entity category
        if hasattr(description, "entity_category"):
            self._attr_entity_category = description.entity_category
        else:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
                
        # Set icon if provided
        if hasattr(description, "icon") and description.icon:
            self._attr_icon = description.icon
        else:
            self._attr_icon = "mdi:car-wrench"
            
        # Set device class
        if hasattr(description, "device_class") and description.device_class:
            self._attr_device_class = description.device_class
            
        # Set options if provided
        if hasattr(description, "options") and description.options:
            self._attr_options = description.options
        
        # Set unit of measurement if provided
        if hasattr(description, "native_unit_of_measurement") and description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement
            
        # Set state class if provided
        if hasattr(description, "state_class") and description.state_class:
            self._attr_state_class = description.state_class
            
        # Force timestamp conversion for specific fields to support Home Assistant expectations
        self._force_timestamp_conversion = (
            self.device_class == SensorDeviceClass.TIMESTAMP or
            "date" in description.key.lower() or
            "time" in description.key.lower() or
            "occurrence" in description.key.lower()
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        try:
            if not self.coordinator.last_update_success:
                _LOGGER.debug("Coordinator has not successfully updated for %s", self.entity_id)
                return None
                
            if not self.coordinator.data:
                _LOGGER.debug("No data available from coordinator for %s", self.entity_id)
                return None
                
            if self.vin not in self.coordinator.data:
                _LOGGER.debug("No data available for vin %s in coordinator data for %s", 
                             self.vin, self.entity_id)
                return None
            
            health_report = self.coordinator.data[self.vin]
            value = search_health_report(health_report, self.entity_description.path)
            
            _LOGGER.debug("Extracting value for %s from path %s: %s", 
                         self.entity_description.name, 
                         self.entity_description.path, 
                         value)
                         
            # Handle datetime/timestamp conversion if needed
            if value is not None and isinstance(value, str):
                # Force conversion for timestamp device class or known timestamp fields 
                if self._force_timestamp_conversion:
                    # Format: YYYYMMDDhhmmss (common in Mazda API)
                    if len(value) == 14 and value.isdigit():
                        try:
                            _LOGGER.debug("Converting Mazda timestamp format '%s' to datetime with timezone", value)
                            dt = datetime.strptime(value, "%Y%m%d%H%M%S")
                            # Add UTC timezone information
                            return dt.replace(tzinfo=timezone.utc)
                        except ValueError as ex:
                            _LOGGER.warning("Failed to parse timestamp '%s': %s", value, ex)
                            # Return original value so sensor still shows something
                            
                    # ISO format with T separator
                    elif "T" in value and ":" in value:
                        try:
                            _LOGGER.debug("Converting ISO format timestamp '%s' to datetime with timezone", value)
                            # Replace Z with +00:00 for UTC timezone
                            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                            # Ensure timezone info is present
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            return dt
                        except ValueError as ex:
                            _LOGGER.warning("Failed to parse ISO timestamp '%s': %s", value, ex)
                            # Return original value so sensor still shows something
                    
                    # Standard date/time format (YYYY-MM-DD HH:MM:SS) as seen in error logs
                    elif value.count("-") == 2 and value.count(":") == 2 and " " in value:
                        try:
                            _LOGGER.debug("Converting standard datetime format '%s' to timezone-aware datetime", value)
                            dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                            # Add UTC timezone information
                            return dt.replace(tzinfo=timezone.utc)
                        except ValueError as ex:
                            _LOGGER.warning("Failed to parse standard datetime '%s': %s", value, ex)
                    
                    # If we're supposed to be a timestamp but couldn't convert it,
                    # log a warning but don't fail the entity
                    _LOGGER.warning(
                        "Received value '%s' for timestamp sensor %s but couldn't convert to datetime", 
                        value, self.entity_id
                    )
                
            # Return the value as-is for non-timestamp types or if conversion failed
            return value
            
        except Exception as ex:
            _LOGGER.error("Error getting native value for %s: %s", self.entity_id, ex)
            return None

    @property
    def available(self):
        """Return if the sensor is available."""
        try:
            # Check if coordinator has data at all
            if not self.coordinator.data:
                _LOGGER.debug("No coordinator data available for sensor %s", self.entity_id)
                return False
                
            # Check if we have data for this vehicle
            if self.vin not in self.coordinator.data:
                _LOGGER.debug("No data available for VIN %s in sensor %s", self.vin, self.entity_id)
                return False
                
            # Get the health report for this VIN
            health_report = self.coordinator.data[self.vin]
            if not health_report:
                _LOGGER.debug("Empty health report for VIN %s in sensor %s", self.vin, self.entity_id) 
                return False
                
            # Check if this sensor's path exists in the data
            value = search_health_report(health_report, self.entity_description.path)
            
            # We consider the sensor available if the value exists (None is a valid value)
            # The key validation is that we can retrieve some data point, even if it's None
            return value is not None or isinstance(value, (bool, int)) or value == 0
                
        except Exception as ex:
            _LOGGER.debug("Error checking availability for %s: %s", self.entity_id, ex)
            return False
