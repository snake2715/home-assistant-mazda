"""The Mazda Connected Services integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import (
    aiohttp_client,
    config_validation as cv,
    device_registry as dr,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CONF_REFRESH_INTERVAL,
    CONF_VEHICLE_INTERVAL,
    CONF_ENDPOINT_INTERVAL,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_REGION,
    DATA_VEHICLES,
    DOMAIN,
)
from .pymazda.client import Client as MazdaAPI
from .pymazda.exceptions import (
    MazdaAccountLockedException,
    MazdaAPIEncryptionException,
    MazdaAuthenticationException,
    MazdaException,
    MazdaTokenExpiredException,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def with_timeout(task, timeout_seconds=30):
    """Run an async task with a timeout."""
    async with asyncio.timeout(timeout_seconds):
        return await task


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mazda Connected Services from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    region = entry.data[CONF_REGION]

    websession = aiohttp_client.async_get_clientsession(hass)
    mazda_client = MazdaAPI(
        email, password, region, websession=websession, use_cached_vehicle_list=True
    )

    try:
        await mazda_client.validate_credentials()
    except MazdaAuthenticationException as ex:
        raise ConfigEntryAuthFailed from ex
    except (
        MazdaException,
        MazdaAccountLockedException,
        MazdaTokenExpiredException,
        MazdaAPIEncryptionException,
    ) as ex:
        _LOGGER.error("Error occurred during Mazda login request: %s", ex)
        raise ConfigEntryNotReady from ex

    async def async_handle_service_call(service_call: ServiceCall) -> None:
        """Handle a service call."""
        # Get device entry from device registry
        dev_reg = dr.async_get(hass)
        device_id = service_call.data["device_id"]
        device_entry = dev_reg.async_get(device_id)
        if TYPE_CHECKING:
            # For mypy: it has already been checked in validate_mazda_device_id
            assert device_entry

        # Get vehicle VIN from device identifiers
        mazda_identifiers = (
            identifier
            for identifier in device_entry.identifiers
            if identifier[0] == DOMAIN
        )
        vin_identifier = next(mazda_identifiers)
        vin = vin_identifier[1]

        # Get vehicle ID and API client from hass.data
        vehicle_id = 0
        api_client = None
        for entry_data in hass.data[DOMAIN].values():
            for vehicle in entry_data[DATA_VEHICLES]:
                if vehicle["vin"] == vin:
                    vehicle_id = vehicle["id"]
                    api_client = entry_data[DATA_CLIENT]
                    break

        if vehicle_id == 0 or api_client is None:
            raise HomeAssistantError("Vehicle ID not found")

        api_method = getattr(api_client, service_call.service)
        try:
            latitude = service_call.data["latitude"]
            longitude = service_call.data["longitude"]
            poi_name = service_call.data["poi_name"]
            await api_method(vehicle_id, latitude, longitude, poi_name)
        except Exception as ex:
            raise HomeAssistantError(ex) from ex

    def validate_mazda_device_id(device_id):
        """Check that a device ID exists in the registry and has at least one 'mazda' identifier."""
        dev_reg = dr.async_get(hass)

        if (device_entry := dev_reg.async_get(device_id)) is None:
            raise vol.Invalid("Invalid device ID")

        mazda_identifiers = [
            identifier
            for identifier in device_entry.identifiers
            if identifier[0] == DOMAIN
        ]
        if not mazda_identifiers:
            raise vol.Invalid("Device ID is not a Mazda vehicle")

        return device_id

    service_schema_send_poi = vol.Schema(
        {
            vol.Required("device_id"): vol.All(cv.string, validate_mazda_device_id),
            vol.Required("latitude"): cv.latitude,
            vol.Required("longitude"): cv.longitude,
            vol.Required("poi_name"): cv.string,
        }
    )

    class MazdaDataUpdateCoordinator(DataUpdateCoordinator):
        def __init__(
            self,
            hass: HomeAssistant,
            client: MazdaAPI,
            config_entry: ConfigEntry,
        ) -> None:
            self.client = client
            self.config_entry = config_entry
            super().__init__(
                hass,
                _LOGGER,
                name=DOMAIN,
                update_interval=timedelta(
                    seconds=config_entry.options.get(
                        CONF_REFRESH_INTERVAL,
                        config_entry.data.get(CONF_REFRESH_INTERVAL, 900)
                    )
                ),
            )
            # Store the intervals for use during updates
            self.vehicle_interval = config_entry.options.get(
                CONF_VEHICLE_INTERVAL,
                config_entry.data.get(CONF_VEHICLE_INTERVAL, 2)
            )
            self.endpoint_interval = config_entry.options.get(
                CONF_ENDPOINT_INTERVAL,
                config_entry.data.get(CONF_ENDPOINT_INTERVAL, 1)
            )

        async def _async_update_data(self):
            """Fetch data from Mazda API."""
            try:
                vehicles = await with_timeout(self.client.get_vehicles())
                _LOGGER.debug("Response from get_vehicles(): %s", vehicles)
                updated_vehicles = []

                for vehicle in vehicles:
                    # Add delay between vehicles
                    if updated_vehicles:  # Don't delay for the first vehicle
                        await asyncio.sleep(self.vehicle_interval)

                    try:
                        vehicle_data = {
                            "id": vehicle.get("id"),
                            "vin": vehicle.get("vin"),
                            "modelYear": vehicle.get("modelYear", "Unknown"),
                            "carlineName": vehicle.get("carlineName", "Unknown"),
                            "isElectric": vehicle.get("isElectric", False)
                        }

                        _LOGGER.debug("Processing vehicle data: %s", vehicle_data)

                        # Get vehicle status
                        vehicle_data["status"] = await with_timeout(
                            self.client.get_vehicle_status(vehicle_data["id"])
                        )
                        _LOGGER.debug("Vehicle status: %s", vehicle_data["status"])
                        
                        # Add delay between endpoints for the same vehicle
                        if self.endpoint_interval > 0:
                            await asyncio.sleep(self.endpoint_interval)

                        if vehicle_data["isElectric"]:
                            # Get EV status
                            vehicle_data["evStatus"] = await with_timeout(
                                self.client.get_ev_vehicle_status(vehicle_data["id"])
                            )
                            _LOGGER.debug("EV status: %s", vehicle_data["evStatus"])
                            
                            # Add delay between endpoints
                            if self.endpoint_interval > 0:
                                await asyncio.sleep(self.endpoint_interval)
                            
                            # Get HVAC settings
                            vehicle_data["hvacSetting"] = await with_timeout(
                                self.client.get_hvac_setting(vehicle_data["id"])
                            )
                            _LOGGER.debug("HVAC settings: %s", vehicle_data["hvacSetting"])

                        updated_vehicles.append(vehicle_data)
                        _LOGGER.debug("Successfully processed vehicle: %s", vehicle_data["vin"])

                    except KeyError as err:
                        _LOGGER.error(
                            "Missing required field %s in vehicle data: %s", 
                            err, 
                            vehicle
                        )
                        continue
                    except Exception as ex:
                        _LOGGER.error(
                            "Error processing vehicle %s: %s", 
                            vehicle.get("vin", "Unknown VIN"), 
                            ex
                        )
                        continue

                if not updated_vehicles:
                    raise UpdateFailed("No vehicles could be processed successfully")

                self.hass.data[DOMAIN][self.config_entry.entry_id][DATA_VEHICLES] = updated_vehicles
                return updated_vehicles

            except MazdaAuthenticationException as ex:
                raise ConfigEntryAuthFailed("Not authenticated") from ex
            except Exception as ex:
                raise UpdateFailed(f"Error communicating with API: {ex}") from ex

    coordinator = MazdaDataUpdateCoordinator(hass, mazda_client, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: mazda_client,
        DATA_COORDINATOR: coordinator,
        DATA_REGION: region,
        DATA_VEHICLES: [],
    }

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    # Setup components
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    hass.services.async_register(
        DOMAIN,
        "send_poi",
        async_handle_service_call,
        schema=service_schema_send_poi,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Only remove services if it is the last config entry
    if len(hass.data[DOMAIN]) == 1:
        hass.services.async_remove(DOMAIN, "send_poi")

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class MazdaEntity(CoordinatorEntity):
    """Defines a base Mazda entity."""

    _attr_has_entity_name = True

    def __init__(self, client, coordinator, index):
        """Initialize the Mazda entity."""
        super().__init__(coordinator)
        self.client = client
        self.index = index
        self.vin = self.data["vin"]
        self.vehicle_id = self.data["id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.vin)},
            manufacturer="Mazda",
            model=f"{self.data['modelYear']} {self.data['carlineName']}",
            name=self.vehicle_name,
        )

    @property
    def data(self):
        """Shortcut to access coordinator data for the entity."""
        return self.coordinator.data[self.index]

    @property
    def vehicle_name(self):
        """Return the vehicle name, to be used as a prefix for names of other entities."""
        if "nickname" in self.data and len(self.data["nickname"]) > 0:
            return self.data["nickname"]
        return f"{self.data['modelYear']} {self.data['carlineName']}"
