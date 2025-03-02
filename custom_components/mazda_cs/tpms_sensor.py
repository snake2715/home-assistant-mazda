"""Platform for Mazda TPMS (Tire Pressure Monitoring System) integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPressure
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MazdaEntity
from .const import (
    DATA_CLIENT, 
    DATA_COORDINATOR, 
    DATA_HEALTH_COORDINATOR, 
    DOMAIN,
    VIN_PREFIX_CX5,
    TPMS_WARNING_DESCRIPTIONS,
    TPMS_WARNING_NORMAL,
    TPMS_WARNING_WARNING,
    TPMS_WARNING_LOW_PRESSURE,
    TPMS_WARNING_CRITICAL,
    TPMS_WARNING_SYSTEM_ERROR,
)

_LOGGER = logging.getLogger(__name__)

@dataclass
class MazdaTPMSSensorRequiredKeysMixin:
    """Mixin for required keys."""

    # Function to determine the value for this sensor
    value_fn: Callable[[dict[str, Any], dict[str, Any]], StateType]


@dataclass
class MazdaTPMSSensorEntityDescription(
    SensorEntityDescription, MazdaTPMSSensorRequiredKeysMixin
):
    """Describes a Mazda TPMS sensor entity."""

    # Function to determine whether the vehicle supports this sensor
    supported_fn: Callable[[dict[str, Any], dict[str, Any]], bool] = lambda data, health_data: True
    entity_category: EntityCategory = EntityCategory.DIAGNOSTIC


def _safe_get_tpms_status(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Safely extract TPMS status from vehicle data."""
    try:
        if not data or "status" not in data:
            return None
        
        tire_pressure = data.get("status", {}).get("tirePressure")
        return tire_pressure
    except (KeyError, AttributeError, TypeError) as err:
        _LOGGER.debug(f"Error getting TPMS status: {err}")
        return None


def _safe_get_tpms_health_data(health_data: Dict[str, Any], vin: str) -> Optional[Dict[str, Any]]:
    """Safely extract TPMS information from health report data."""
    try:
        if not health_data or not vin or vin not in health_data:
            return None
        
        vehicle_health = health_data.get(vin, {})
        
        # Check if we have remoteInfos data
        remote_infos = vehicle_health.get("remoteInfos", [])
        if not remote_infos or len(remote_infos) == 0:
            return None
            
        # Get TPMS information from the first remote info
        tpms_info = remote_infos[0].get("TPMSInformation")
        return tpms_info
    except (KeyError, AttributeError, TypeError, IndexError) as err:
        _LOGGER.debug(f"Error getting TPMS health data: {err}")
        return None


def _tpms_supported(data: Dict[str, Any], health_data: Dict[str, Any]) -> bool:
    """Check if TPMS is supported using both regular status and health data."""
    # First check status data
    tire_pressure = _safe_get_tpms_status(data)
    if tire_pressure and any(tire_pressure.get(k) is not None for k in [
        "frontLeftTirePressurePsi", 
        "frontRightTirePressurePsi",
        "rearLeftTirePressurePsi", 
        "rearRightTirePressurePsi"
    ]):
        return True
    
    # Then check health data
    vin = data.get("vin", "")
    tpms_info = _safe_get_tpms_health_data(health_data, vin)
    if tpms_info and any(tpms_info.get(k) is not None for k in [
        "FLTPrsDispPsi", 
        "FRTPrsDispPsi", 
        "RLTPrsDispPsi", 
        "RRTPrsDispPsi",
        "TPMSStatus"
    ]):
        return True
    
    return False


def _is_status_data_source_supported(data: Dict[str, Any], position_key: str) -> bool:
    """Check if specific tire position is supported in status data."""
    try:
        tire_pressure = _safe_get_tpms_status(data)
        if not tire_pressure:
            return False
        
        return position_key in tire_pressure and tire_pressure[position_key] is not None
    except (KeyError, AttributeError, TypeError) as err:
        _LOGGER.debug(f"Error checking status data support for {position_key}: {err}")
        return False


def _is_health_data_source_supported(health_data: Dict[str, Any], vin: str, position_key: str) -> bool:
    """Check if specific tire position is supported in health data."""
    try:
        tpms_info = _safe_get_tpms_health_data(health_data, vin)
        if not tpms_info:
            return False
        
        return position_key in tpms_info and tpms_info[position_key] is not None
    except (KeyError, AttributeError, TypeError) as err:
        _LOGGER.debug(f"Error checking health data support for {position_key}: {err}")
        return False


def _fl_tire_pressure_supported(data: Dict[str, Any], health_data: Dict[str, Any]) -> bool:
    """Check if front left tire pressure is supported."""
    # Check status data
    if _is_status_data_source_supported(data, "frontLeftTirePressurePsi"):
        return True
    
    # Check health data
    vin = data.get("vin", "")
    return _is_health_data_source_supported(health_data, vin, "FLTPrsDispPsi")


def _fr_tire_pressure_supported(data: Dict[str, Any], health_data: Dict[str, Any]) -> bool:
    """Check if front right tire pressure is supported."""
    # Check status data
    if _is_status_data_source_supported(data, "frontRightTirePressurePsi"):
        return True
    
    # Check health data
    vin = data.get("vin", "")
    return _is_health_data_source_supported(health_data, vin, "FRTPrsDispPsi")


def _rl_tire_pressure_supported(data: Dict[str, Any], health_data: Dict[str, Any]) -> bool:
    """Check if rear left tire pressure is supported."""
    # Check status data
    if _is_status_data_source_supported(data, "rearLeftTirePressurePsi"):
        return True
    
    # Check health data
    vin = data.get("vin", "")
    return _is_health_data_source_supported(health_data, vin, "RLTPrsDispPsi")


def _rr_tire_pressure_supported(data: Dict[str, Any], health_data: Dict[str, Any]) -> bool:
    """Check if rear right tire pressure is supported."""
    # Check status data
    if _is_status_data_source_supported(data, "rearRightTirePressurePsi"):
        return True
    
    # Check health data
    vin = data.get("vin", "")
    return _is_health_data_source_supported(health_data, vin, "RRTPrsDispPsi")


def _tpms_status_supported(data: Dict[str, Any], health_data: Dict[str, Any]) -> bool:
    """Check if TPMS overall status is supported."""
    # This is only in health data
    vin = data.get("vin", "")
    return _is_health_data_source_supported(health_data, vin, "TPMSStatus")


def _get_tire_pressure_value(data: Dict[str, Any], health_data: Dict[str, Any], 
                          status_key: str, health_key: str) -> Optional[float]:
    """Get tire pressure value from either status or health data."""
    try:
        # First try from status
        tire_pressure = _safe_get_tpms_status(data)
        if tire_pressure and status_key in tire_pressure and tire_pressure[status_key] is not None:
            try:
                return float(tire_pressure[status_key])
            except (ValueError, TypeError):
                _LOGGER.debug(f"Could not convert tire pressure value {tire_pressure[status_key]} to float")
        
        # Then try from health data
        vin = data.get("vin", "")
        tpms_info = _safe_get_tpms_health_data(health_data, vin)
        if tpms_info and health_key in tpms_info and tpms_info[health_key] is not None:
            try:
                return float(tpms_info[health_key])
            except (ValueError, TypeError):
                _LOGGER.debug(f"Could not convert health tire pressure value {tpms_info[health_key]} to float")
                
        return None
    except Exception as err:
        _LOGGER.debug(f"Error getting tire pressure value: {err}")
        return None


def _get_tire_warning_level(data: Dict[str, Any], health_data: Dict[str, Any], tire_position: str) -> Optional[int]:
    """Get tire warning level based on position.
    
    Supports both individual TPMS sensors and the CX-5's single TPMS sensor behavior.
    """
    try:
        vin = data.get("vin", "")
        
        # Default position mappings for health data
        position_to_health_key = {
            "front_left_tire_pressure": "FLTWarnDisp",
            "front_right_tire_pressure": "FRTWarnDisp",
            "rear_left_tire_pressure": "RLTWarnDisp",
            "rear_right_tire_pressure": "RRTWarnDisp"
        }
        
        # Position mappings for status data
        position_to_status_key = {
            "front_left_tire_pressure": "frontLeftTirePressureWarning",
            "front_right_tire_pressure": "frontRightTirePressureWarning",
            "rear_left_tire_pressure": "rearLeftTirePressureWarning",
            "rear_right_tire_pressure": "rearRightTirePressureWarning"
        }
        
        # Check if this is a CX-5 with single TPMS sensor
        is_cx5_single_sensor = False
        if vin.startswith(VIN_PREFIX_CX5):
            is_cx5_single_sensor = True
            _LOGGER.debug(f"Detected CX-5 vehicle with single TPMS sensor: {vin}")
        else:
            # Check model name as well
            model_info = data.get("modelInfo", {})
            model_name = model_info.get("model", "").lower()
            if "cx-5" in model_name or "cx5" in model_name:
                is_cx5_single_sensor = True
                _LOGGER.debug(f"Detected CX-5 vehicle with single TPMS sensor: {model_name}")
        
        # Get TPMS information from health data
        tpms_info = _safe_get_tpms_health_data(health_data, vin)
        
        # For CX-5 with single sensor, use the overall TPMS status for all tires if in health data
        if is_cx5_single_sensor and tpms_info:
            # First try to get the overall status
            if "TPMSStatus" in tpms_info:
                return int(tpms_info["TPMSStatus"])
            
            # If overall status not available, use the first non-null warning we find
            for key in position_to_health_key.values():
                if key in tpms_info and tpms_info[key] is not None:
                    try:
                        return int(tpms_info[key])
                    except (ValueError, TypeError):
                        continue
        
        # Try to get specific tire warning from health data
        if tpms_info:
            health_key = position_to_health_key.get(tire_position)
            if health_key and health_key in tpms_info and tpms_info[health_key] is not None:
                try:
                    return int(tpms_info[health_key])
                except (ValueError, TypeError):
                    pass
        
        # If no health data or couldn't find in health data, try status data
        tire_pressure = _safe_get_tpms_status(data)
        if tire_pressure:
            status_key = position_to_status_key.get(tire_position)
            
            # For CX-5 with single sensor in status data
            if is_cx5_single_sensor:
                # Look for any non-normal warning
                warning_values = {}
                for key in position_to_status_key.values():
                    if key in tire_pressure and tire_pressure[key] is not None:
                        try:
                            value = int(tire_pressure[key])
                            warning_values[value] = value
                        except (ValueError, TypeError):
                            continue
                
                # Return the highest warning value (most severe)
                if warning_values:
                    return max(warning_values.values())
            
            # Otherwise get specific tire warning
            if status_key and status_key in tire_pressure and tire_pressure[status_key] is not None:
                try:
                    return int(tire_pressure[status_key])
                except (ValueError, TypeError):
                    pass
        
        return None
    except Exception as err:
        _LOGGER.debug(f"Error getting tire warning level: {err}")
        return None


def _fl_tire_pressure_value(data: Dict[str, Any], health_data: Dict[str, Any]) -> Optional[float]:
    """Get front left tire pressure value."""
    return _get_tire_pressure_value(data, health_data, "frontLeftTirePressurePsi", "FLTPrsDispPsi")


def _fr_tire_pressure_value(data: Dict[str, Any], health_data: Dict[str, Any]) -> Optional[float]:
    """Get front right tire pressure value."""
    return _get_tire_pressure_value(data, health_data, "frontRightTirePressurePsi", "FRTPrsDispPsi")


def _rl_tire_pressure_value(data: Dict[str, Any], health_data: Dict[str, Any]) -> Optional[float]:
    """Get rear left tire pressure value."""
    return _get_tire_pressure_value(data, health_data, "rearLeftTirePressurePsi", "RLTPrsDispPsi")


def _rr_tire_pressure_value(data: Dict[str, Any], health_data: Dict[str, Any]) -> Optional[float]:
    """Get rear right tire pressure value."""
    return _get_tire_pressure_value(data, health_data, "rearRightTirePressurePsi", "RRTPrsDispPsi")


def _tpms_status_value(data: Dict[str, Any], health_data: Dict[str, Any]) -> Optional[int]:
    """Get TPMS overall status value."""
    try:
        vin = data.get("vin", "")
        tpms_info = _safe_get_tpms_health_data(health_data, vin)
        
        # First try to get it directly from health data
        if tpms_info and "TPMSStatus" in tpms_info and tpms_info["TPMSStatus"] is not None:
            try:
                return int(tpms_info["TPMSStatus"])
            except (ValueError, TypeError):
                pass
        
        # Check if this is a CX-5 (which uses a single sensor)
        is_cx5_single_sensor = False
        if vin.startswith(VIN_PREFIX_CX5):
            is_cx5_single_sensor = True
        else:
            # Check model name as well
            model_info = data.get("modelInfo", {})
            model_name = model_info.get("model", "").lower()
            if "cx-5" in model_name or "cx5" in model_name:
                is_cx5_single_sensor = True
        
        # For CX-5, we'll use the warning level from any tire since they all use the same sensor
        if is_cx5_single_sensor:
            # Try each tire position and take the first valid value
            positions = ["front_left_tire_pressure", "front_right_tire_pressure", 
                         "rear_left_tire_pressure", "rear_right_tire_pressure"]
            
            for position in positions:
                warning_level = _get_tire_warning_level(data, health_data, position)
                if warning_level is not None:
                    return warning_level
        
        # For other models, if any tire has a warning, that's the overall status
        warning_levels = []
        for position in ["front_left_tire_pressure", "front_right_tire_pressure", 
                         "rear_left_tire_pressure", "rear_right_tire_pressure"]:
            warning_level = _get_tire_warning_level(data, health_data, position)
            if warning_level is not None:
                warning_levels.append(warning_level)
        
        # Return the highest warning level found (most severe)
        if warning_levels:
            return max(warning_levels)
        
        # Default to normal if no warnings found but tires are detected
        if _tpms_supported(data, health_data):
            return TPMS_WARNING_NORMAL
            
        return None
    except Exception as err:
        _LOGGER.debug(f"Error getting TPMS status: {err}")
        return None


# Define all the sensor entities for TPMS
TPMS_SENSOR_ENTITIES = [
    MazdaTPMSSensorEntityDescription(
        key="front_left_tire_pressure",
        name="Front Left Tire Pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.PSI,
        supported_fn=_fl_tire_pressure_supported,
        value_fn=_fl_tire_pressure_value,
        icon="mdi:car-tire-alert",
    ),
    MazdaTPMSSensorEntityDescription(
        key="front_right_tire_pressure",
        name="Front Right Tire Pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.PSI,
        supported_fn=_fr_tire_pressure_supported,
        value_fn=_fr_tire_pressure_value,
        icon="mdi:car-tire-alert",
    ),
    MazdaTPMSSensorEntityDescription(
        key="rear_left_tire_pressure",
        name="Rear Left Tire Pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.PSI,
        supported_fn=_rl_tire_pressure_supported,
        value_fn=_rl_tire_pressure_value,
        icon="mdi:car-tire-alert",
    ),
    MazdaTPMSSensorEntityDescription(
        key="rear_right_tire_pressure",
        name="Rear Right Tire Pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.PSI,
        supported_fn=_rr_tire_pressure_supported,
        value_fn=_rr_tire_pressure_value,
        icon="mdi:car-tire-alert",
    ),
    MazdaTPMSSensorEntityDescription(
        key="tpms_status",
        name="TPMS Status",
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=_tpms_status_supported,
        value_fn=_tpms_status_value,
        icon="mdi:tire",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Mazda TPMS sensors from config entry."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    health_coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_HEALTH_COORDINATOR]

    entities = []

    for vehicle_index, vehicle in enumerate(coordinator.data):
        # Skip vehicles that are not registered with Mazda Connected Services
        if not vehicle.get("vin"):
            continue

        # For each sensor type
        for description in TPMS_SENSOR_ENTITIES:
            if description.supported_fn(vehicle, health_coordinator.data):
                entities.append(
                    MazdaTPMSSensorEntity(
                        client, coordinator, health_coordinator, vehicle_index, description
                    )
                )

    async_add_entities(entities)


class MazdaTPMSSensorEntity(MazdaEntity, SensorEntity):
    """Representation of a Mazda TPMS sensor."""

    entity_description: MazdaTPMSSensorEntityDescription

    def __init__(
        self, 
        client, 
        coordinator, 
        health_coordinator, 
        index, 
        description
    ):
        """Initialize Mazda TPMS sensor."""
        super().__init__(client, coordinator, index)
        self.entity_description = description
        self._health_coordinator = health_coordinator
        self._attr_unique_id = f"{self.vin}_{description.key}"
        
        # Add the entity to the vehicle device group
        self._attr_has_entity_name = True

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        try:
            # Get data from vehicle and health coordinators
            vehicle_data = self.coordinator.data[self.index]
            health_data = self._health_coordinator.data
            
            # Call the value function
            return self.entity_description.value_fn(vehicle_data, health_data)
        except (KeyError, IndexError, TypeError, ValueError) as err:
            _LOGGER.debug(
                f"Error getting native value for {self.entity_description.key}: {err}"
            )
            return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {}
        
        try:
            # Add health report timestamp if available
            vin = self.coordinator.data[self.index].get("vin", "")
            if self._health_coordinator.data and vin in self._health_coordinator.data:
                remote_infos = self._health_coordinator.data[vin].get("remoteInfos", [])
                if remote_infos and len(remote_infos) > 0:
                    # Add measurement date if available
                    tpms_info = remote_infos[0].get("TPMSInformation", {})
                    if tpms_info:
                        # Add measurement date if available
                        year = tpms_info.get("TPrsDispYear")
                        month = tpms_info.get("TPrsDispMonth")
                        day = tpms_info.get("TPrsDispDate")
                        hour = tpms_info.get("TPrsDispHour")
                        minute = tpms_info.get("TPrsDispMinute")
                        
                        if all(x is not None for x in [year, month, day, hour, minute]):
                            attributes["measurement_time"] = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
                        
                        # Add more information for specific sensor types
                        if self.entity_description.key == "tpms_status":
                            tpms_status = tpms_info.get("TPMSStatus")
                            if tpms_status is not None:
                                attributes["status_code"] = tpms_status
                                attributes["status_description"] = self._get_tpms_status_description(tpms_status)
                                
                            system_fault = tpms_info.get("TPMSSystemFlt")
                            if system_fault is not None:
                                attributes["system_fault"] = bool(system_fault)
        except Exception as err:
            _LOGGER.debug(f"Error getting extra attributes: {err}")
            
        return attributes

    def _get_tpms_status_description(self, status_code):
        """Get a human-readable description for the TPMS status code."""
        status_descriptions = {
            0: "Normal",
            1: "Low Pressure Warning",
            2: "High Pressure Warning",
            3: "System Fault",
            4: "Sensor Not Detected"
        }
        return status_descriptions.get(status_code, f"Unknown ({status_code})")
