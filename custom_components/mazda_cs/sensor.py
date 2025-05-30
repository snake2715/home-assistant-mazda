"""Platform for Mazda sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
from .const import DATA_CLIENT, DATA_COORDINATOR, DATA_HEALTH_COORDINATOR, DATA_VEHICLES, DOMAIN


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
    return (data["hasFuel"]) and (
        data["status"]["fuelRemainingPercent"] is not None
    )


def _fuel_distance_remaining_supported(data):
    """Determine if fuel distance remaining is supported."""
    return (data["hasFuel"]) and (
        data["status"]["fuelDistanceRemainingKm"] is not None
    )


def _front_left_tire_pressure_supported(data):
    """Determine if front left tire pressure is supported."""
    # Check standard location first
    if "status" in data and "tirePressure" in data["status"] and data["status"]["tirePressure"]["frontLeftTirePressurePsi"] is not None:
        return True
    
    # Check remoteInfos location for CX-5
    if "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "FLTPrsDispPsi" in remote_info["TPMSInformation"]:
            return remote_info["TPMSInformation"]["FLTPrsDispPsi"] is not None
    
    return False


def _front_right_tire_pressure_supported(data):
    """Determine if front right tire pressure is supported."""
    # Check standard location first
    if "status" in data and "tirePressure" in data["status"] and data["status"]["tirePressure"]["frontRightTirePressurePsi"] is not None:
        return True
    
    # Check remoteInfos location for CX-5
    if "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "FRTPrsDispPsi" in remote_info["TPMSInformation"]:
            return remote_info["TPMSInformation"]["FRTPrsDispPsi"] is not None
    
    return False


def _rear_left_tire_pressure_supported(data):
    """Determine if rear left tire pressure is supported."""
    # Check standard location first
    if "status" in data and "tirePressure" in data["status"] and data["status"]["tirePressure"]["rearLeftTirePressurePsi"] is not None:
        return True
    
    # Check remoteInfos location for CX-5
    if "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "RLTPrsDispPsi" in remote_info["TPMSInformation"]:
            return remote_info["TPMSInformation"]["RLTPrsDispPsi"] is not None
    
    return False


def _rear_right_tire_pressure_supported(data):
    """Determine if rear right tire pressure is supported."""
    # Check standard location first
    if "status" in data and "tirePressure" in data["status"] and data["status"]["tirePressure"]["rearRightTirePressurePsi"] is not None:
        return True
    
    # Check remoteInfos location for CX-5
    if "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "RRTPrsDispPsi" in remote_info["TPMSInformation"]:
            return remote_info["TPMSInformation"]["RRTPrsDispPsi"] is not None
    
    return False


def _tpms_status_supported(data):
    """Determine if TPMS status is supported."""
    if "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "TPMSStatus" in remote_info["TPMSInformation"]:
            return True
    return False


def _tpms_system_fault_supported(data):
    """Determine if TPMS system fault is supported."""
    if "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "TPMSSystemFlt" in remote_info["TPMSInformation"]:
            return True
    return False


def _ev_charge_level_supported(data):
    """Determine if charge level is supported."""
    return (
        data["isElectric"]
        and data["evStatus"]["chargeInfo"]["batteryLevelPercentage"] is not None
    )

def _ev_remaining_charging_time_supported(data):
    """Determine if remaining changing time is supported."""
    return (
        data["isElectric"]
        and data["evStatus"]["chargeInfo"]["basicChargeTimeMinutes"] is not None
    )

def _ev_remaining_range_supported(data):
    """Determine if remaining range is supported."""
    return (
        data["isElectric"]
        and data["evStatus"]["chargeInfo"]["drivingRangeKm"] is not None
    )

def _ev_remaining_bev_range_supported(data):
    """Determine if remaining range bev is supported."""
    return (
        data["isElectric"]
        and data["evStatus"]["chargeInfo"]["drivingRangeBevKm"] is not None
    )


def _fuel_distance_remaining_value(data):
    """Get the fuel distance remaining value."""
    return round(data["status"]["fuelDistanceRemainingKm"])


def _odometer_value(data):
    """Get the odometer value."""
    # In order to match the behavior of the Mazda mobile app, we always round down
    return int(data["status"]["odometerKm"])


def _front_left_tire_pressure_value(data):
    """Get the front left tire pressure value."""
    if "status" in data and "tirePressure" in data["status"] and data["status"]["tirePressure"]["frontLeftTirePressurePsi"] is not None:
        return round(data["status"]["tirePressure"]["frontLeftTirePressurePsi"])
    elif "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "FLTPrsDispPsi" in remote_info["TPMSInformation"]:
            return round(remote_info["TPMSInformation"]["FLTPrsDispPsi"])
    return None


def _front_right_tire_pressure_value(data):
    """Get the front right tire pressure value."""
    if "status" in data and "tirePressure" in data["status"] and data["status"]["tirePressure"]["frontRightTirePressurePsi"] is not None:
        return round(data["status"]["tirePressure"]["frontRightTirePressurePsi"])
    elif "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "FRTPrsDispPsi" in remote_info["TPMSInformation"]:
            return round(remote_info["TPMSInformation"]["FRTPrsDispPsi"])
    return None


def _rear_left_tire_pressure_value(data):
    """Get the rear left tire pressure value."""
    if "status" in data and "tirePressure" in data["status"] and data["status"]["tirePressure"]["rearLeftTirePressurePsi"] is not None:
        return round(data["status"]["tirePressure"]["rearLeftTirePressurePsi"])
    elif "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "RLTPrsDispPsi" in remote_info["TPMSInformation"]:
            return round(remote_info["TPMSInformation"]["RLTPrsDispPsi"])
    return None


def _rear_right_tire_pressure_value(data):
    """Get the rear right tire pressure value."""
    if "status" in data and "tirePressure" in data["status"] and data["status"]["tirePressure"]["rearRightTirePressurePsi"] is not None:
        return round(data["status"]["tirePressure"]["rearRightTirePressurePsi"])
    elif "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "RRTPrsDispPsi" in remote_info["TPMSInformation"]:
            return round(remote_info["TPMSInformation"]["RRTPrsDispPsi"])
    return None


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


def _tpms_status_value(data):
    """Get the TPMS status value."""
    if "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "TPMSStatus" in remote_info["TPMSInformation"]:
            return remote_info["TPMSInformation"]["TPMSStatus"]
    return None


def _tpms_system_fault_value(data):
    """Get the TPMS system fault value."""
    if "remoteInfos" in data and len(data["remoteInfos"]) > 0:
        remote_info = data["remoteInfos"][0]
        if "TPMSInformation" in remote_info and "TPMSSystemFlt" in remote_info["TPMSInformation"]:
            return remote_info["TPMSInformation"]["TPMSSystemFlt"]
    return None


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
    MazdaSensorEntityDescription(
        key="tpms_status",
        translation_key="tpms_status",
        icon="mdi:car-tire-alert",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_tpms_status_supported,
        value=_tpms_status_value,
    ),
    MazdaSensorEntityDescription(
        key="tpms_system_fault",
        translation_key="tpms_system_fault",
        icon="mdi:car-tire-alert",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_tpms_system_fault_supported,
        value=_tpms_system_fault_value,
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
    health_coordinators = hass.data[DOMAIN][config_entry.entry_id][DATA_HEALTH_COORDINATOR]
    vehicles = hass.data[DOMAIN][config_entry.entry_id][DATA_VEHICLES]

    entities: list[SensorEntity] = []

    for index, data in enumerate(coordinator.data):
        for description in SENSOR_ENTITIES:
            if description.is_supported(data):
                entities.append(
                    MazdaSensorEntity(client, coordinator, index, description)
                )

    async_add_entities(entities)
    
    # Set up health sensors
    from .health_sensor import async_setup_health_sensors
    await async_setup_health_sensors(hass, config_entry, async_add_entities)


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