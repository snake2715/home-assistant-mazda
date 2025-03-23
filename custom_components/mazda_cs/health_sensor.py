"""Health sensor implementation for Mazda Connected Services."""
import logging
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    DATA_CLIENT,
    DATA_HEALTH_COORDINATOR,
    DATA_VEHICLES,
    DEFAULT_TEMPLATE,
    GENERAL_HEALTH_TEMPLATE,
    MODEL_TEMPLATE_MAP,
    CX5_HEALTH_TEMPLATE,
    CX30_HEALTH_TEMPLATE,
    MAZDA3_HEALTH_TEMPLATE,
)

_LOGGER = logging.getLogger(__name__)

# Cache for template selection by VIN
_TEMPLATE_CACHE = {}
# Cache for valid data paths by VIN
_VALID_PATHS_CACHE = {}

def _get_template_for_vin(vin):
    """Get the appropriate template for a VIN, with caching."""
    if vin in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[vin]
    
    # Default to general template
    template = GENERAL_HEALTH_TEMPLATE
    
    # Check for specific model templates based on VIN prefix
    for prefix, model_name in MODEL_TEMPLATE_MAP.items():
        if vin.startswith(prefix):
            if model_name == "CX5":
                template = CX5_HEALTH_TEMPLATE
            elif model_name == "CX30":
                template = CX30_HEALTH_TEMPLATE
            elif model_name == "MAZDA3":
                template = MAZDA3_HEALTH_TEMPLATE
            break
    
    # Cache the result
    _TEMPLATE_CACHE[vin] = template
    return template

def _convert_entity_category(category_str):
    """Convert string entity category to the proper enum value."""
    if category_str == "diagnostic":
        return EntityCategory.DIAGNOSTIC
    elif category_str == "config":
        return EntityCategory.CONFIG
    return None

async def async_setup_health_sensors(hass, config_entry, async_add_entities):
    """Set up the health sensor platform."""
    try:
        client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
        health_coordinators = hass.data[DOMAIN][config_entry.entry_id][DATA_HEALTH_COORDINATOR]
        vehicles = hass.data[DOMAIN][config_entry.entry_id][DATA_VEHICLES]
        
        entities = []
        
        # Initialize valid paths cache for each vehicle
        for i, vehicle in enumerate(vehicles):
            vin = vehicle["vin"]
            if vin not in _VALID_PATHS_CACHE:
                _VALID_PATHS_CACHE[vin] = set()
                
            # Get the template for this vehicle
            template = _get_template_for_vin(vin)
            
            # Get the health coordinator for this vehicle
            health_coordinator = health_coordinators[i]
            
            # Check if we have health data
            has_health_data = False
            health_report = None
            if health_coordinator.data and "health_report" in health_coordinator.data:
                health_report = health_coordinator.data["health_report"]
                has_health_data = health_report is not None
            
            # Create sensors based on the template
            for data_path, sensor_config in template.items():
                # Check if the data path exists in the health report
                path_exists = False
                if data_path in _VALID_PATHS_CACHE[vin]:
                    path_exists = True
                elif has_health_data:
                    # Only check if we have health data
                    value = get_value_from_path(health_report, data_path)
                    if value is not None:
                        path_exists = True
                        _VALID_PATHS_CACHE[vin].add(data_path)
                
                # Always create the sensor, even if the data isn't available yet
                entities.append(
                    MazdaHealthSensor(
                        health_coordinator,
                        vin,
                        data_path,
                        sensor_config.get("name", data_path),
                        sensor_config.get("icon"),
                        sensor_config.get("device_class"),
                        sensor_config.get("state_class"),
                        sensor_config.get("unit_of_measurement"),
                        _convert_entity_category(sensor_config.get("entity_category")),
                        vehicle_info={
                            "api_data": {
                                "nickname": vehicle.get("nickname", ""),
                                "model_name": vehicle.get("carlineName", ""),
                                "model_year": vehicle.get("modelYear", ""),
                                "model_code": vehicle.get("modelCode", ""),
                            }
                        },
                        config=sensor_config
                    )
                )
            
            _LOGGER.info(
                "Created health sensors for %s", 
                vehicle.get("nickname", "") if vehicle else vin
            )
            
        _LOGGER.info("Adding %d health sensor entities", len(entities))
        async_add_entities(entities)
            
    except Exception as ex:
        _LOGGER.error("Error setting up health sensors: %s", str(ex))

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor platform."""
    await async_setup_health_sensors(hass, config_entry, async_add_entities)

def get_value_from_path(data, path):
    """Get a value from a nested dictionary using a dot-separated path."""
    if not data or not path:
        return None
        
    # Try direct access first
    try:
        value = get_value_from_nested_dict(data, path)
        if value is not None:
            return value
    except (KeyError, TypeError, AttributeError):
        pass
        
    # Try handling special cases like arrays and nested objects
    parts = path.split(".")
    
    # Special handling for TPMSInformation paths
    if len(parts) > 1 and parts[0] == "TPMSInformation":
        # Check if TPMSInformation is directly in the data
        if "TPMSInformation" in data and isinstance(data["TPMSInformation"], dict):
            # Try to get the value from the nested TPMSInformation object
            try:
                return get_value_from_nested_dict(data["TPMSInformation"], parts[1])
            except (KeyError, TypeError, AttributeError):
                pass
                
        # Check if TPMSInformation is in remoteInfos
        if "remoteInfos" in data and isinstance(data["remoteInfos"], list):
            for item in data["remoteInfos"]:
                if "TPMSInformation" in item and isinstance(item["TPMSInformation"], dict):
                    try:
                        return get_value_from_nested_dict(item["TPMSInformation"], parts[1])
                    except (KeyError, TypeError, AttributeError):
                        continue
    
    # Special handling for OilMntInformation paths
    if len(parts) > 1 and parts[0] == "OilMntInformation":
        # Check if OilMntInformation is directly in the data
        if "OilMntInformation" in data and isinstance(data["OilMntInformation"], dict):
            # Try to get the value from the nested OilMntInformation object
            try:
                return get_value_from_nested_dict(data["OilMntInformation"], parts[1])
            except (KeyError, TypeError, AttributeError):
                pass
                
        # Check if OilMntInformation is in remoteInfos
        if "remoteInfos" in data and isinstance(data["remoteInfos"], list):
            for item in data["remoteInfos"]:
                if "OilMntInformation" in item and isinstance(item["OilMntInformation"], dict):
                    try:
                        return get_value_from_nested_dict(item["OilMntInformation"], parts[1])
                    except (KeyError, TypeError, AttributeError):
                        continue
    
    # Handle remoteInfos array - a common pattern in Mazda API responses
    if len(parts) > 1 and parts[0] == "remoteInfos" and isinstance(data.get("remoteInfos"), list):
        # Extract the item index if specified (e.g., remoteInfos.0.value)
        if len(parts) > 2 and parts[1].isdigit():
            index = int(parts[1])
            if index < len(data["remoteInfos"]):
                return get_value_from_nested_dict(data["remoteInfos"][index], ".".join(parts[2:]))
        
        # If no index specified, try to find by matching the InfoType
        if len(parts) > 2 and parts[1] != "InfoType":
            # Try to find an item with InfoType matching the second path component
            for item in data["remoteInfos"]:
                if item.get("InfoType") == parts[1]:
                    return get_value_from_nested_dict(item, ".".join(parts[2:]))
    
    # Handle array lookups without using remoteInfos prefix
    if len(parts) > 1 and isinstance(data.get(parts[0]), list):
        array = data.get(parts[0])
        if parts[1].isdigit():
            # Numerical index specified
            index = int(parts[1])
            if index < len(array):
                return get_value_from_nested_dict(array[index], ".".join(parts[2:]))
        else:
            # Try to find by key matching
            for item in array:
                # If the second path component is a key in the item, look in that item
                if isinstance(item, dict) and parts[1] in item:
                    return get_value_from_nested_dict(item, ".".join(parts[1:]))
                    
    return None

def get_value_from_nested_dict(data, path):
    """Navigate a nested dictionary using dot notation path."""
    if not data or not path:
        return None
        
    if not isinstance(data, dict):
        return None
        
    if "." not in path:
        return data.get(path)
        
    parts = path.split(".")
    current = data
    
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
            if current is None:
                return None
        else:
            return None
            
    return current

class MazdaHealthSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Mazda health sensor."""
    
    def __init__(
                self,
                coordinator,
                vin,
                path,
                name,
                icon,
                device_class,
                state_class,
                unit_of_measurement,
                entity_category,
                vehicle_info=None,
                config=None
            ):
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._vin = vin
        self._path = path
        self._name = name
        self._icon = icon
        self._device_class = device_class
        self._state_class = state_class
        self._unit_of_measurement = unit_of_measurement
        self._entity_category = entity_category
        self._vehicle_info = vehicle_info
        self._last_value = None  # Cache for use in failure recovery
        self._config = config or {}  # Initialize config with empty dict if not provided
        
        # Create a unique_id based on VIN and data path
        self._unique_id = f"{DOMAIN}_{vin}_health_{path}"
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
                "data_path": self._path,
                "sensor_type": "health",
            }

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
        if self._device_class == "timestamp":
            return SensorDeviceClass.TIMESTAMP
        elif self._device_class == "temperature":
            return SensorDeviceClass.TEMPERATURE
        elif self._device_class == "pressure":
            return SensorDeviceClass.PRESSURE
        elif self._device_class == "date":
            return SensorDeviceClass.DATE
        return self._device_class

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        if self._state_class == "measurement":
            return SensorStateClass.MEASUREMENT
        elif self._state_class == "total":
            return SensorStateClass.TOTAL
        elif self._state_class == "total_increasing":
            return SensorStateClass.TOTAL_INCREASING
        return self._state_class

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        if self._unit_of_measurement == "km":
            return UnitOfLength.KILOMETERS
        elif self._unit_of_measurement == "mi":
            return UnitOfLength.MILES
        elif self._unit_of_measurement == "kPa":
            return UnitOfPressure.KPA
        elif self._unit_of_measurement == "psi":
            return UnitOfPressure.PSI
        elif self._unit_of_measurement == "°C":
            return UnitOfTemperature.CELSIUS
        elif self._unit_of_measurement == "%":
            return PERCENTAGE
        return self._unit_of_measurement

    @property
    def entity_category(self):
        """Return the entity category."""
        return self._entity_category

    @property
    def path(self):
        """Return the data path of the sensor."""
        return self._path

    @property
    def native_value(self):
        """Return the state of the sensor."""
        try:
            # Get the health report from the coordinator
            if not self.coordinator.data or "health_report" not in self.coordinator.data:
                _LOGGER.debug(
                    "No health report data available for %s (path: %s)",
                    self.name,
                    self.path,
                )
                return self._last_value
                
            health_report = self.coordinator.data["health_report"]
            
            # Debug logging to help diagnose issues
            _LOGGER.debug(
                "Getting value for health sensor %s (path: %s)",
                self.name,
                self.path,
            )
            
            # Get the value from the health report using the path
            value = get_value_from_path(health_report, self.path)
            
            # Process the value if needed (e.g., apply value maps)
            processed_value = self._process_value(value)
            
            # Cache the value for use in failure recovery
            if processed_value is not None:
                self._last_value = processed_value
                
            _LOGGER.debug(
                "Health sensor %s (path: %s) value: %s, processed: %s",
                self.name,
                self.path,
                value,
                processed_value,
            )
            
            return processed_value
        except Exception as ex:
            _LOGGER.error(
                "Error processing value %s for %s: %s",
                self.coordinator.data.get("health_report", {}) if self.coordinator.data else None,
                self.entity_id,
                ex,
            )
            return self._last_value

    def _process_value(self, value):
        """Process the value according to the sensor configuration."""
        try:
            # Return None if value is None
            if value is None:
                return None
                
            # Check if we have a value map
            if "value_map" in self._config and str(value) in self._config["value_map"]:
                _LOGGER.debug("Mapping value %s using value_map for %s", value, self.entity_id)
                return self._config["value_map"][str(value)]
            
            # Special handling for CX-5 TPMS status
            if self.path == "TPMSInformation.TPMSStatus":
                status_map = {
                    "0": "Normal",
                    "1": "Warning",
                    "2": "Low Pressure",
                    "3": "Critical",
                    "4": "System Error"
                }
                if str(value) in status_map:
                    return status_map[str(value)]
                
            # Special handling for CX-5 TPMS system fault
            if self.path == "TPMSInformation.TPMSSystemFlt":
                fault_map = {
                    "0": "Normal",
                    "1": "Fault Detected"
                }
                if str(value) in fault_map:
                    return fault_map[str(value)]
                
            # Convert to the appropriate type
            if self._device_class == "timestamp":
                # Handle timestamp conversion
                if isinstance(value, str):
                    try:
                        # Try parsing as ISO format
                        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        return dt
                    except (ValueError, AttributeError):
                        # Try parsing as Unix timestamp
                        try:
                            return datetime.fromtimestamp(float(value), timezone.utc)
                        except (ValueError, TypeError):
                            # Try parsing Mazda format: YYYYMMDDhhmmss
                            try:
                                if len(value) == 14:
                                    year = int(value[0:4])
                                    month = int(value[4:6])
                                    day = int(value[6:8])
                                    hour = int(value[8:10])
                                    minute = int(value[10:12])
                                    second = int(value[12:14])
                                    dt = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
                                    return dt
                            except (ValueError, TypeError, IndexError):
                                pass
                            
                            _LOGGER.warning("Could not parse timestamp: %s", value)
                            return None
                elif isinstance(value, (int, float)):
                    # Assume Unix timestamp
                    return datetime.fromtimestamp(value, timezone.utc)
                return value
            elif self._device_class == "temperature":
                # Convert to float for temperature
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return value
            elif self._device_class == "pressure":
                # Convert to float for pressure
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return value
            elif isinstance(value, (int, float)) and self._unit_of_measurement:
                # For numeric values with units, ensure they're the right type
                return float(value)
            
            # For all other types, return as is
            return value
        except Exception as ex:
            _LOGGER.error("Error processing value %s for %s: %s", value, self.entity_id, ex)
            return None

    @property
    def available(self):
        """Return True if entity is available."""
        # Custom availability logic - we consider the entity available if:
        # 1. The coordinator is available AND has data, OR
        # 2. We have cached a previous value that we can use
        
        coordinator_has_data = (
            self.coordinator and 
            self.coordinator.data is not None and
            "health_report" in self.coordinator.data and
            self.coordinator.data["health_report"] is not None
        )
        
        has_cached_value = self._last_value is not None
            
        # If we have either coordinator data or a cached value, the entity is available
        return coordinator_has_data or has_cached_value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attr_extra_state_attributes
