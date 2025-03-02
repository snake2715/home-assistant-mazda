"""Platform for Mazda sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any, Dict, Optional

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
    UnitOfTime,
)
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
    TPMS_WARNING_DESCRIPTIONS,
)

# Import TPMS sensor functionality
from .tpms_sensor import (
    _safe_get_tpms_status,
    _safe_get_tpms_health_data,
    _tpms_supported,
    _fl_tire_pressure_supported as _front_left_tire_pressure_supported,
    _fr_tire_pressure_supported as _front_right_tire_pressure_supported, 
    _rl_tire_pressure_supported as _rear_left_tire_pressure_supported,
    _rr_tire_pressure_supported as _rear_right_tire_pressure_supported,
    _tpms_status_supported,
    _fl_tire_pressure_value as _front_left_tire_pressure_value,
    _fr_tire_pressure_value as _front_right_tire_pressure_value,
    _rl_tire_pressure_value as _rear_left_tire_pressure_value,
    _rr_tire_pressure_value as _rear_right_tire_pressure_value,
    _tpms_status_value,
    _get_tire_warning_level,
)

_LOGGER = logging.getLogger(__name__)

@dataclass
class MazdaSensorRequiredKeysMixin:
    """Mixin for required keys."""

    # Function to determine the value for this sensor, given the coordinator data
    # and the configured unit system
    value: Callable[[dict[str, Any]], StateType]


@dataclass
class MazdaSensorEntityDescription(
    SensorEntityDescription, MazdaSensorRequiredKeysMixin
):
    """Describes a Mazda sensor entity."""

    # Function to determine whether the vehicle supports this sensor,
    # given the coordinator data
    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True


def _fuel_remaining_percentage_supported(data):
    """Determine if fuel remaining percentage is supported."""
    if data is None or "isElectric" not in data:
        return False
    
    if data.get("status") is None:
        return False
        
    return (not data["isElectric"]) and (
        "fuelRemainingPercent" in data["status"] and
        data["status"]["fuelRemainingPercent"] is not None
    )


def _fuel_distance_remaining_supported(data):
    """Determine if fuel distance remaining is supported."""
    if data is None or "isElectric" not in data:
        return False
    
    if data.get("status") is None:
        return False
        
    return (not data["isElectric"]) and (
        data.get("status", {}).get("fuelDistanceRemainingKm") is not None
    )


def _ev_charge_level_supported(data):
    """Determine if charge level is supported."""
    if data is None or "isElectric" not in data:
        return False
        
    if not data["isElectric"]:
        return False
        
    if data.get("evStatus") is None or data["evStatus"].get("chargeInfo") is None:
        return False
        
    return "batteryLevelPercentage" in data["evStatus"]["chargeInfo"] and data["evStatus"]["chargeInfo"]["batteryLevelPercentage"] is not None

def _ev_remaining_charging_time_supported(data):
    """Determine if remaining changing time is supported."""
    if data is None or "isElectric" not in data:
        return False
        
    if not data["isElectric"]:
        return False
        
    if data.get("evStatus") is None or data["evStatus"].get("chargeInfo") is None:
        return False
        
    return "basicChargeTimeMinutes" in data["evStatus"]["chargeInfo"] and data["evStatus"]["chargeInfo"]["basicChargeTimeMinutes"] is not None

def _ev_remaining_range_supported(data):
    """Determine if remaining range is supported."""
    if data is None or "isElectric" not in data:
        return False
        
    if not data["isElectric"]:
        return False
        
    if data.get("evStatus") is None or data["evStatus"].get("chargeInfo") is None:
        return False
        
    return "drivingRangeKm" in data["evStatus"]["chargeInfo"] and data["evStatus"]["chargeInfo"]["drivingRangeKm"] is not None

def _ev_remaining_bev_range_supported(data):
    """Determine if remaining range bev is supported."""
    if data is None or "isElectric" not in data:
        return False
        
    if not data["isElectric"]:
        return False
        
    if data.get("evStatus") is None or data["evStatus"].get("chargeInfo") is None:
        return False
        
    return "drivingRangeBevKm" in data["evStatus"]["chargeInfo"] and data["evStatus"]["chargeInfo"]["drivingRangeBevKm"] is not None

def _engine_state_supported(data):
    """Determine if the engine state sensor is supported for this vehicle."""
    try:
        if not data or not data.get("status"):
            return False
            
        electrical = data["status"].get("electricalInformation")
        if not electrical:
            return False
            
        # Check if EngineState key exists
        return "EngineState" in electrical
    except (KeyError, TypeError, AttributeError):
        return False


def _power_control_status_supported(data):
    """Determine if the power control status sensor is supported for this vehicle."""
    try:
        if not data or not data.get("status"):
            return False
            
        electrical = data["status"].get("electricalInformation")
        if not electrical:
            return False
            
        # Check if PowerControlStatus key exists
        return "PowerControlStatus" in electrical
    except (KeyError, TypeError, AttributeError):
        return False


def _fuel_distance_remaining_value(data):
    """Get the fuel distance remaining value."""
    return round(data["status"]["fuelDistanceRemainingKm"])


def _odometer_value(data):
    """Get the odometer value."""
    # In order to match the behavior of the Mazda mobile app, we always round down
    return int(data["status"]["odometerKm"])


def _ev_charge_level_value(data):
    """Get the charge level value."""
    return round(data["evStatus"]["chargeInfo"]["batteryLevelPercentage"])

def _ev_remaining_charging_time_value(data):
    """Get the remaining changing time value."""
    return round(data["evStatus"]["chargeInfo"]["basicChargeTimeMinutes"])

def _ev_remaining_range_value(data):
    """Get the remaining range value."""
    return round(data["evStatus"]["chargeInfo"]["drivingRangeKm"])

def _ev_remaining_range_bev_value(data):
    """Get the remaining range BEV value."""
    return round(data["evStatus"]["chargeInfo"]["drivingRangeBevKm"])

def _engine_state_value(data):
    """Get the engine state value."""
    try:
        if not data or not data.get("status"):
            return None
            
        electrical = data["status"].get("electricalInformation")
        if not electrical:
            return None
            
        return electrical.get("EngineState")
    except (KeyError, TypeError, AttributeError) as e:
        # Log error but don't crash
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.error("Error getting engine state: %s", str(e))
        return None


def _power_control_status_value(data):
    """Get the power control status value."""
    try:
        if not data or not data.get("status"):
            return None
            
        electrical = data["status"].get("electricalInformation")
        if not electrical:
            return None
            
        return electrical.get("PowerControlStatus")
    except (KeyError, TypeError, AttributeError) as e:
        # Log error but don't crash
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.error("Error getting power control status: %s", str(e))
        return None


SENSOR_ENTITIES = [
    MazdaSensorEntityDescription(
        key="fuel_remaining_percentage",
        translation_key="fuel_remaining_percentage",
        icon="mdi:gas-station",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_fuel_remaining_percentage_supported,
        value=lambda data: data.get("status", {}).get("fuelRemainingPercent") if data else None,
    ),
    MazdaSensorEntityDescription(
        key="fuel_distance_remaining",
        translation_key="fuel_distance_remaining",
        icon="mdi:gas-station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_fuel_distance_remaining_supported,
        value=lambda data: data.get("status", {}).get("fuelDistanceRemainingKm") if data else None,
    ),
    MazdaSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        is_supported=lambda data: data.get("status", {}).get("odometerKm") is not None,
        value=lambda data: int(data.get("status", {}).get("odometerKm")) if data else None,
    ),
    MazdaSensorEntityDescription(
        key="front_left_tire_pressure",
        translation_key="front_left_tire_pressure",
        icon="mdi:car-tire-alert",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data, health_data: _front_left_tire_pressure_supported(data, health_data),
        value=lambda data, health_data: _front_left_tire_pressure_value(data, health_data),
    ),
    MazdaSensorEntityDescription(
        key="front_right_tire_pressure",
        translation_key="front_right_tire_pressure",
        icon="mdi:car-tire-alert",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data, health_data: _front_right_tire_pressure_supported(data, health_data),
        value=lambda data, health_data: _front_right_tire_pressure_value(data, health_data),
    ),
    MazdaSensorEntityDescription(
        key="rear_left_tire_pressure",
        translation_key="rear_left_tire_pressure",
        icon="mdi:car-tire-alert",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data, health_data: _rear_left_tire_pressure_supported(data, health_data),
        value=lambda data, health_data: _rear_left_tire_pressure_value(data, health_data),
    ),
    MazdaSensorEntityDescription(
        key="rear_right_tire_pressure",
        translation_key="rear_right_tire_pressure",
        icon="mdi:car-tire-alert",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=lambda data, health_data: _rear_right_tire_pressure_supported(data, health_data),
        value=lambda data, health_data: _rear_right_tire_pressure_value(data, health_data),
    ),
    MazdaSensorEntityDescription(
        key="ev_charge_level",
        translation_key="ev_charge_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_charge_level_supported,
        value=lambda data: data.get("evStatus", {}).get("chargeInfo", {}).get("batteryLevelPercentage") if data else None,
    ),
    MazdaSensorEntityDescription(
        key="ev_remaining_charging_time",
        translation_key="ev_remaining_charging_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_remaining_charging_time_supported,
        value=lambda data: data.get("evStatus", {}).get("chargeInfo", {}).get("basicChargeTimeMinutes") if data else None,
    ),
    MazdaSensorEntityDescription(
        key="ev_remaining_range",
        translation_key="ev_remaining_range",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_remaining_range_supported,
        value=lambda data: data.get("evStatus", {}).get("chargeInfo", {}).get("drivingRangeKm") if data else None,
    ),
    MazdaSensorEntityDescription(
        key="ev_remaining_range_bev",
        translation_key="ev_remaining_range_bev",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_remaining_bev_range_supported,
        value=lambda data: data.get("evStatus", {}).get("chargeInfo", {}).get("drivingRangeBevKm") if data else None,
    ),
    MazdaSensorEntityDescription(
        key="engine_state",
        translation_key="engine_state",
        icon="mdi:engine",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_engine_state_supported,
        value=lambda data: data.get("status", {}).get("electricalInformation", {}).get("EngineState") if data else None,
    ),
    MazdaSensorEntityDescription(
        key="power_control_status",
        translation_key="power_control_status",
        icon="mdi:car-electric",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_power_control_status_supported,
        value=lambda data: data.get("status", {}).get("electricalInformation", {}).get("PowerControlStatus") if data else None,
    ),
    MazdaSensorEntityDescription(
        key="tpms_status",
        translation_key="tpms_status",
        icon="mdi:car-tire-alert",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_tpms_status_supported,
        value=_tpms_status_value,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Mazda vehicle sensor platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    health_coordinator = hass.data[DOMAIN][config_entry.entry_id].get(DATA_HEALTH_COORDINATOR)

    entities = []
    
    # Debug log to identify what we're seeing in the coordinator data
    _LOGGER.debug(f"Setting up sensors with coordinator data: {coordinator.data}")
    
    # For each vehicle in the coordinator data
    for index, vehicle in enumerate(coordinator.data):
        vin = vehicle.get("vin")
        _LOGGER.debug(f"Processing vehicle {index}: VIN={vin}, Name={vehicle.get('nickname', 'Unknown')}")
        
        # Check which sensors are supported for this vehicle
        for description in SENSOR_ENTITIES:
            try:
                # Check if the sensor is supported
                is_supported = False
                
                # Get the required parameter count for the is_supported function
                # Regular sensors take 1 parameter, TPMS sensors take 2
                param_count = description.is_supported.__code__.co_argcount
                
                if param_count == 1:
                    # Regular sensor with 1 parameter
                    is_supported = description.is_supported(vehicle)
                elif param_count == 2:
                    # TPMS sensor with 2 parameters
                    is_supported = description.is_supported(vehicle, health_coordinator.data if health_coordinator else None)
                else:
                    _LOGGER.warning(f"Unsupported parameter count {param_count} for sensor {description.key}")
                
                if is_supported:
                    _LOGGER.debug(f"Adding sensor {description.key} for vehicle {vin}")
                    entities.append(
                        MazdaSensorEntity(
                            client=client,
                            coordinator=coordinator,
                            health_coordinator=health_coordinator,
                            index=index,
                            description=description,
                        )
                    )
            except Exception as ex:
                _LOGGER.error(f"Failed to check sensor {description.key}: {ex}")
    
    # If we have any entities, add them
    if entities:
        _LOGGER.info(f"Adding {len(entities)} Mazda sensor entities")
        async_add_entities(entities)
    else:
        _LOGGER.warning("No Mazda sensors were created")

    # Also set up health sensors
    if DATA_HEALTH_COORDINATOR in hass.data[DOMAIN][config_entry.entry_id]:
        try:
            from .health_sensor import async_setup_entry as async_setup_health_sensor
            await async_setup_health_sensor(hass, config_entry, async_add_entities)
        except Exception as ex:
            _LOGGER.error("Failed to set up Mazda health sensors: %s", ex)


class MazdaSensorEntity(MazdaEntity, SensorEntity):
    """Representation of a Mazda vehicle sensor."""

    entity_description: MazdaSensorEntityDescription

    def __init__(self, client, coordinator, health_coordinator, index, description):
        """Initialize Mazda sensor."""
        super().__init__(client, coordinator, index)
        self.entity_description = description
        self.health_coordinator = health_coordinator

        self._attr_unique_id = f"{self.vin}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        try:
            if self.data is None:
                return None
                
            if self.entity_description.key in ["front_left_tire_pressure", "front_right_tire_pressure", "rear_left_tire_pressure", "rear_right_tire_pressure", "tpms_status"]:
                return self.entity_description.value(self.data, self.health_coordinator.data if self.health_coordinator else None)
            else:
                return self.entity_description.value(self.data)
        except Exception as e:
            _LOGGER.debug("Error getting native value for %s: %s", self.entity_description.key, str(e))
            return None

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes of the sensor."""
        attrs = {}
        
        try:
            # Add TPMS warning description if this is a tire pressure sensor
            if self.entity_description.key in ["front_left_tire_pressure", "front_right_tire_pressure", "rear_left_tire_pressure", "rear_right_tire_pressure"]:
                if self.data is None or self.health_coordinator is None or self.health_coordinator.data is None:
                    return attrs
                    
                warning_level = _get_tire_warning_level(self.data, self.health_coordinator.data, self.entity_description.key)
                if warning_level:
                    attrs["warning_level"] = warning_level
        except Exception as e:
            _LOGGER.debug("Error getting extra state attributes for %s: %s", self.entity_description.key, str(e))
            
        return attrs
