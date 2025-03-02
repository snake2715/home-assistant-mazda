"""Platform for Mazda binary sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MazdaEntity
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN


@dataclass
class MazdaBinarySensorRequiredKeysMixin:
    """Mixin for required keys."""

    # Function to determine the value for this binary sensor, given the coordinator data
    value_fn: Callable[[dict[str, Any]], bool]


@dataclass
class MazdaBinarySensorEntityDescription(
    BinarySensorEntityDescription, MazdaBinarySensorRequiredKeysMixin
):
    """Describes a Mazda binary sensor entity."""

    # Function to determine whether the vehicle supports this binary sensor, given the coordinator data
    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True


def _plugged_in_supported(data):
    """Determine if 'plugged in' binary sensor is supported."""
    try:
        if not data or not data.get("isElectric", False):
            return False
            
        # Check if vehicle has ev status and charge info
        ev_status = data.get("evStatus", {})
        if not ev_status:
            return False
            
        charge_info = ev_status.get("chargeInfo", {})
        if not charge_info:
            return False
            
        # Only return True if pluggedIn field exists
        return "pluggedIn" in charge_info
    except (KeyError, TypeError, AttributeError):
        return False


def _safe_get_door_status(data, door_key, default=False):
    """Safely access door status with proper None checking.
    
    Args:
        data: The vehicle data dictionary
        door_key: The specific door key to access
        default: Default value if data is missing
        
    Returns:
        Door state or default value if any part of the path is None
    """
    try:
        if not data:
            return default
        status = data.get("status")
        if not status:
            return default
        doors = status.get("doors")
        if not doors:
            return default
        return doors.get(door_key, default)
    except (TypeError, AttributeError, KeyError):
        return default


def _safe_get_engine_status(data, status_field):
    """Safely get the engine status from the vehicle data.
    
    This function safely accesses the engine status values from the vehicle data,
    gracefully handling any missing or null data.
    
    The API returns two main engine-related fields:
    - PowerControlStatus: Indicates if the vehicle is off (0), on but engine not running (1),
      or if the engine is running (2)
    - EngineState: More detailed state with values like initial state (0), off (1),
      starting (2), running (3), or stopping (4)
    
    Args:
        data: The vehicle data dictionary
        status_field: The specific field to check (PowerControlStatus or EngineState)
        
    Returns:
        The status value or None if not available
    """
    try:
        if not data:
            return None
        
        status = data.get("status")
        if not status:
            return None
            
        electrical = status.get("electricalInformation")
        if not electrical:
            return None
            
        return electrical.get(status_field)
    except (KeyError, TypeError, AttributeError) as e:
        # Log error but don't crash
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.error("Error getting engine status for %s: %s", status_field, str(e))
        return None

def _is_engine_running(data):
    """Function to determine if the engine is running.
    
    Uses the PowerControlStatus field to determine engine state.
    
    PowerControlStatus values:
    - 0: Off (vehicle completely off)
    - 1: On but engine not running (accessory mode)
    - 2: Engine running
    
    Returns:
        True if engine is running, False otherwise
    """
    power_status = _safe_get_engine_status(data, "PowerControlStatus")
    return power_status == 2

def _engine_status_supported(data):
    """Determine if the engine status sensor is supported for this vehicle."""
    if not data:
        return False
        
    # Check if we have status data at all
    if data.get("status") is None:
        return False
        
    # Check if we have electrical information in the status
    electrical = data.get("status", {}).get("electricalInformation")
    if not electrical:
        return False
        
    # Check if PowerControlStatus is present
    return "PowerControlStatus" in electrical


BINARY_SENSOR_ENTITIES = [
    MazdaBinarySensorEntityDescription(
        key="driver_door",
        translation_key="driver_door",
        icon="mdi:car-door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: _safe_get_door_status(data, "driverDoorOpen"),
    ),
    MazdaBinarySensorEntityDescription(
        key="passenger_door",
        translation_key="passenger_door",
        icon="mdi:car-door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: _safe_get_door_status(data, "passengerDoorOpen"),
    ),
    MazdaBinarySensorEntityDescription(
        key="rear_left_door",
        translation_key="rear_left_door",
        icon="mdi:car-door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: _safe_get_door_status(data, "rearLeftDoorOpen"),
    ),
    MazdaBinarySensorEntityDescription(
        key="rear_right_door",
        translation_key="rear_right_door",
        icon="mdi:car-door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: _safe_get_door_status(data, "rearRightDoorOpen"),
    ),
    MazdaBinarySensorEntityDescription(
        key="trunk",
        translation_key="trunk",
        icon="mdi:car-back",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: _safe_get_door_status(data, "trunkOpen"),
    ),
    MazdaBinarySensorEntityDescription(
        key="hood",
        translation_key="hood",
        icon="mdi:car",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: _safe_get_door_status(data, "hoodOpen"),
    ),
    MazdaBinarySensorEntityDescription(
        key="ev_plugged_in",
        translation_key="ev_plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        is_supported=_plugged_in_supported,
        value_fn=lambda data: data.get("evStatus", {}).get("chargeInfo", {}).get("pluggedIn", False) if data and data.get("evStatus") and data.get("evStatus").get("chargeInfo") else False,
    ),
    MazdaBinarySensorEntityDescription(
        key="engine_running",
        translation_key="engine_running",
        icon="mdi:engine",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_supported=_engine_status_supported,
        value_fn=_is_engine_running,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    async_add_entities(
        MazdaBinarySensorEntity(client, coordinator, index, description)
        for index, data in enumerate(coordinator.data)
        for description in BINARY_SENSOR_ENTITIES
        if description.is_supported(data)
    )


class MazdaBinarySensorEntity(MazdaEntity, BinarySensorEntity):
    """Representation of a Mazda vehicle binary sensor."""

    entity_description: MazdaBinarySensorEntityDescription

    def __init__(self, client, coordinator, index, description):
        """Initialize Mazda binary sensor."""
        super().__init__(client, coordinator, index)
        self.entity_description = description

        self._attr_unique_id = f"{self.vin}_{description.key}"

    @property
    def is_on(self):
        """Return the state of the binary sensor."""
        try:
            if not self.data:
                return None
            return self.entity_description.value_fn(self.data)
        except (KeyError, TypeError, AttributeError) as e:
            # Log error but don't crash
            import logging
            _LOGGER = logging.getLogger(__name__)
            _LOGGER.error("Error getting binary sensor state for %s: %s", self.entity_description.key, str(e))
            return None
