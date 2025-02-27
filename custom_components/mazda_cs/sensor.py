"""Platform for Mazda sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import MazdaEntity
from .const import DATA_CLIENT, DATA_COORDINATOR, DATA_HEALTH_COORDINATOR, DOMAIN

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


def _front_left_tire_pressure_supported(data):
    """Determine if front left tire pressure is supported."""
    if data is None or data.get("status") is None:
        return False
    
    tire_pressure = data["status"].get("tirePressure")
    if tire_pressure is None:
        return False
        
    return "frontLeftTirePressurePsi" in tire_pressure and tire_pressure["frontLeftTirePressurePsi"] is not None


def _front_right_tire_pressure_supported(data):
    """Determine if front right tire pressure is supported."""
    if data is None or data.get("status") is None:
        return False
    
    tire_pressure = data["status"].get("tirePressure")
    if tire_pressure is None:
        return False
        
    return "frontRightTirePressurePsi" in tire_pressure and tire_pressure["frontRightTirePressurePsi"] is not None


def _rear_left_tire_pressure_supported(data):
    """Determine if rear left tire pressure is supported."""
    if data is None or data.get("status") is None:
        return False
    
    tire_pressure = data["status"].get("tirePressure")
    if tire_pressure is None:
        return False
        
    return "rearLeftTirePressurePsi" in tire_pressure and tire_pressure["rearLeftTirePressurePsi"] is not None


def _rear_right_tire_pressure_supported(data):
    """Determine if rear right tire pressure is supported."""
    if data is None or data.get("status") is None:
        return False
    
    tire_pressure = data["status"].get("tirePressure")
    if tire_pressure is None:
        return False
        
    return "rearRightTirePressurePsi" in tire_pressure and tire_pressure["rearRightTirePressurePsi"] is not None


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

def _fuel_distance_remaining_value(data):
    """Get the fuel distance remaining value."""
    return round(data["status"]["fuelDistanceRemainingKm"])


def _odometer_value(data):
    """Get the odometer value."""
    # In order to match the behavior of the Mazda mobile app, we always round down
    return int(data["status"]["odometerKm"])


def _front_left_tire_pressure_value(data):
    """Get the front left tire pressure value."""
    return round(data["status"]["tirePressure"]["frontLeftTirePressurePsi"])


def _front_right_tire_pressure_value(data):
    """Get the front right tire pressure value."""
    return round(data["status"]["tirePressure"]["frontRightTirePressurePsi"])


def _rear_left_tire_pressure_value(data):
    """Get the rear left tire pressure value."""
    return round(data["status"]["tirePressure"]["rearLeftTirePressurePsi"])


def _rear_right_tire_pressure_value(data):
    """Get the rear right tire pressure value."""
    return round(data["status"]["tirePressure"]["rearRightTirePressurePsi"])


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


SENSOR_ENTITIES = [
    MazdaSensorEntityDescription(
        key="fuel_remaining_percentage",
        translation_key="fuel_remaining_percentage",
        icon="mdi:gas-station",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_fuel_remaining_percentage_supported,
        value=lambda data: data["status"]["fuelRemainingPercent"],
    ),
    MazdaSensorEntityDescription(
        key="fuel_distance_remaining",
        translation_key="fuel_distance_remaining",
        icon="mdi:gas-station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_fuel_distance_remaining_supported,
        value=_fuel_distance_remaining_value,
    ),
    MazdaSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        is_supported=lambda data: data["status"]["odometerKm"] is not None,
        value=_odometer_value,
    ),
    MazdaSensorEntityDescription(
        key="front_left_tire_pressure",
        translation_key="front_left_tire_pressure",
        icon="mdi:car-tire-alert",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_front_left_tire_pressure_supported,
        value=_front_left_tire_pressure_value,
    ),
    MazdaSensorEntityDescription(
        key="front_right_tire_pressure",
        translation_key="front_right_tire_pressure",
        icon="mdi:car-tire-alert",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_front_right_tire_pressure_supported,
        value=_front_right_tire_pressure_value,
    ),
    MazdaSensorEntityDescription(
        key="rear_left_tire_pressure",
        translation_key="rear_left_tire_pressure",
        icon="mdi:car-tire-alert",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_rear_left_tire_pressure_supported,
        value=_rear_left_tire_pressure_value,
    ),
    MazdaSensorEntityDescription(
        key="rear_right_tire_pressure",
        translation_key="rear_right_tire_pressure",
        icon="mdi:car-tire-alert",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.PSI,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_rear_right_tire_pressure_supported,
        value=_rear_right_tire_pressure_value,
    ),
    MazdaSensorEntityDescription(
        key="ev_charge_level",
        translation_key="ev_charge_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_charge_level_supported,
        value=_ev_charge_level_value,
    ),
    MazdaSensorEntityDescription(
        key="ev_remaining_charging_time",
        translation_key="ev_remaining_charging_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_remaining_charging_time_supported,
        value=_ev_remaining_charging_time_value,
    ),
    MazdaSensorEntityDescription(
        key="ev_remaining_range",
        translation_key="ev_remaining_range",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_remaining_range_supported,
        value=_ev_remaining_range_value,
    ),
    MazdaSensorEntityDescription(
        key="ev_remaining_range_bev",
        translation_key="ev_remaining_range_bev",
        icon="mdi:ev-station",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_ev_remaining_bev_range_supported,
        value=_ev_remaining_range_bev_value,
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

    entities = []
    
    # Debug log to identify what we're seeing in the coordinator data
    _LOGGER.debug(f"Setting up sensors with coordinator data: {coordinator.data}")
    
    # For each vehicle in the coordinator data
    for index, vehicle in enumerate(coordinator.data):
        vin = vehicle.get("vin")
        _LOGGER.debug(f"Processing vehicle {index}: VIN={vin}, Name={vehicle.get('nickname', 'Unknown')}")
        
        # Check which sensors are supported for this vehicle
        for description in SENSOR_ENTITIES:
            if description.is_supported(vehicle):
                _LOGGER.debug(f"Adding sensor {description.key} for vehicle {vin}")
                entities.append(
                    MazdaSensorEntity(
                        client=client,
                        coordinator=coordinator,
                        index=index,
                        description=description,
                    )
                )
    
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

    def __init__(self, client, coordinator, index, description):
        """Initialize Mazda sensor."""
        super().__init__(client, coordinator, index)
        self.entity_description = description

        self._attr_unique_id = f"{self.vin}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value(self.data)
