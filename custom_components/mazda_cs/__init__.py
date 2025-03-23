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

from .const import DATA_CLIENT, DATA_COORDINATOR, DATA_HEALTH_COORDINATOR, DATA_REGION, DATA_VEHICLES, DOMAIN
from .health_coordinator import MazdaHealthUpdateCoordinator
from .api_lock import RequestPriority, get_account_lock
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

# Health sensors will be registered separately in the sensor platform setup
# PLATFORMS.append("health_sensor")

# Default settings
DEFAULT_TIMEOUT = 60  # seconds
DEFAULT_VEHICLE_UPDATE_INTERVAL = 300  # seconds
DEFAULT_VEHICLE_DELAY = 1  # seconds delay between updating each vehicle


async def with_timeout(task, timeout_seconds=DEFAULT_TIMEOUT):
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
        account_email = None
        for entry_id, entry_data in hass.data[DOMAIN].items():
            for vehicle in entry_data[DATA_VEHICLES]:
                if vehicle["vin"] == vin:
                    vehicle_id = vehicle["id"]
                    api_client = entry_data[DATA_CLIENT]
                    # Get the account email from the entry data
                    config_entry = hass.config_entries.async_get_entry(entry_id)
                    if config_entry:
                        account_email = config_entry.data.get(CONF_EMAIL)
                    break

        if vehicle_id == 0 or api_client is None:
            raise HomeAssistantError("Vehicle ID not found")

        api_method = getattr(api_client, service_call.service)
        
        # Get the account lock
        account_lock = get_account_lock(account_email or email)
        
        # Use the lock with COMMAND priority (highest)
        async with account_lock.acquire_context(
            RequestPriority.COMMAND,
            f"service_{service_call.service}"
        ):
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

    async def async_update_data():
        """Fetch data from Mazda API."""
        # Get the account lock
        account_lock = get_account_lock(email)
        
        # Use the lock with STATUS priority (medium)
        async with account_lock.acquire_context(
            RequestPriority.STATUS,
            "vehicle_status_refresh"
        ):
            try:
                vehicles = await with_timeout(mazda_client.get_vehicles())
    
                # The Mazda API can throw an error when multiple simultaneous requests are
                # made for the same account, so we can only make one request at a time here
                for vehicle in vehicles:
                    vehicle["status"] = await with_timeout(
                        mazda_client.get_vehicle_status(vehicle["id"])
                    )
    
                    # If vehicle is electric, get additional EV-specific status info
                    if vehicle["isElectric"]:
                        vehicle["evStatus"] = await with_timeout(
                            mazda_client.get_ev_vehicle_status(vehicle["id"])
                        )
                        vehicle["hvacSetting"] = await with_timeout(
                            mazda_client.get_hvac_setting(vehicle["id"])
                        )
                    
                    # Add a delay between vehicles to reduce API load
                    if vehicles.index(vehicle) < len(vehicles) - 1:  # Don't delay after the last vehicle
                        _LOGGER.debug("Waiting %s seconds before updating next vehicle", DEFAULT_VEHICLE_DELAY)
                        await asyncio.sleep(DEFAULT_VEHICLE_DELAY)
    
                hass.data[DOMAIN][entry.entry_id][DATA_VEHICLES] = vehicles
    
                return vehicles
            except MazdaAuthenticationException as ex:
                raise ConfigEntryAuthFailed("Not authenticated with Mazda API") from ex
            except Exception as ex:
                _LOGGER.exception(
                    "Unknown error occurred during Mazda update request: %s", ex
                )
                raise UpdateFailed(ex) from ex

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=DEFAULT_VEHICLE_UPDATE_INTERVAL),
    )

    # Initialize health coordinators for each vehicle
    health_coordinators = []
    vehicles = await with_timeout(mazda_client.get_vehicles())
    
    for vehicle in vehicles:
        # Create health coordinator for this vehicle
        health_coordinator = MazdaHealthUpdateCoordinator(
            hass,
            mazda_client,
            vehicle["id"],
            DEFAULT_VEHICLE_UPDATE_INTERVAL,  # Use the same update interval as vehicle status
            email,  # Pass the account email for lock management
        )
        health_coordinators.append(health_coordinator)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: mazda_client,
        DATA_COORDINATOR: coordinator,
        DATA_HEALTH_COORDINATOR: health_coordinators,
        DATA_REGION: region,
        DATA_VEHICLES: vehicles,
    }

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()
    
    # Fetch initial health data immediately to ensure sensors have data
    for health_coordinator in health_coordinators:
        try:
            await health_coordinator.async_config_entry_first_refresh()
            _LOGGER.debug("Initial health data fetched successfully for vehicle %s", health_coordinator.vehicle_id)
        except Exception as ex:
            _LOGGER.error("Error fetching initial health data for vehicle %s: %s", health_coordinator.vehicle_id, ex)

    # Setup components
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    hass.services.async_register(
        DOMAIN,
        "send_poi",
        async_handle_service_call,
        schema=service_schema_send_poi,
    )
    
    # Register service to manually refresh health data
    async def async_handle_refresh_health(service_call: ServiceCall) -> None:
        """Handle a request to manually refresh health data."""
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

        # Find the health coordinator for this vehicle
        for entry_id, entry_data in hass.data[DOMAIN].items():
            if DATA_HEALTH_COORDINATOR not in entry_data:
                continue
                
            health_coordinators = entry_data[DATA_HEALTH_COORDINATOR]
            for coordinator in health_coordinators:
                if coordinator.vehicle and coordinator.vehicle.get("vin") == vin:
                    # Get the account email from the entry data
                    config_entry = hass.config_entries.async_get_entry(entry_id)
                    account_email = config_entry.data.get(CONF_EMAIL) if config_entry else None
                    
                    # Get the account lock
                    account_lock = get_account_lock(account_email or email)
                    
                    # Use the lock with COMMAND priority (highest) for manual refresh
                    async with account_lock.acquire_context(
                        RequestPriority.COMMAND,
                        f"manual_health_refresh_{coordinator.vehicle_id}"
                    ):
                        _LOGGER.info("Manually refreshing health data for vehicle %s", vin)
                        await coordinator.async_refresh()
                    return
                    
        _LOGGER.error("Could not find health coordinator for vehicle %s", vin)
        raise HomeAssistantError(f"Vehicle {vin} not found or health data not available")

    # Register service schema for refresh_health
    service_schema_refresh_health = vol.Schema(
        {
            vol.Required("device_id"): vol.All(cv.string, validate_mazda_device_id),
        }
    )
    
    hass.services.async_register(
        DOMAIN,
        "refresh_health",
        async_handle_refresh_health,
        schema=service_schema_refresh_health,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Only remove services if it is the last config entry
    if len(hass.data[DOMAIN]) == 1:
        hass.services.async_remove(DOMAIN, "send_poi")
        hass.services.async_remove(DOMAIN, "refresh_health")

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
        
        # Get detailed model information
        model_details = self._get_model_with_details()
        
        # Create a more descriptive model string with line breaks
        # Line 1: Year and model
        model_str = model_details["vehicle"]
        
        # Line 2: Engine/trim details
        if model_details["engine"]:
            model_str += f"\n{model_details['engine']}"
            
        # Line 3: Color
        if model_details["color"]:
            model_str += f"\n{model_details['color']}"
        
        # Line 4: Nickname if available
        nickname = self.data.get("nickname", "")
        if nickname:
            model_str += f"\nNickname: {nickname}"
            
        # Line 5: VIN (last 6 digits for privacy)
        vin_display = self.vin[-6:] if self.vin else ""
        if vin_display:
            model_str += f"\nVIN: ...{vin_display}"
            
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.vin)},
            manufacturer="Mazda",
            model=model_str,
            name=self.vehicle_name,
            # Add additional attributes that will show up in the device info
            suggested_area="Garage",
            # Include the raw data for diagnostics
            configuration_url=f"https://www.mazdausa.com/mymazda",
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

    def _get_model_with_details(self):
        """Return a detailed model string with year, model, and trim."""
        model_year = self.data.get('modelYear', '')
        model_name = self.data.get('modelName', self.data.get('carlineName', ''))
        
        # Extract the base model from carlineName (e.g., "CX-30" from "CX-30 2.5 S SES")
        base_model = model_name.split(' ')[0] if ' ' in model_name else model_name
        
        # Extract the trim/engine info (everything after the model name)
        trim_info = ' '.join(model_name.split(' ')[1:]) if ' ' in model_name else ''
        
        # Construct the vehicle and engine parts
        vehicle = f"{model_year} {base_model}"
        engine = trim_info
        
        # Get the exterior color
        color = self.data.get('exteriorColorName', '')
        
        return {
            "vehicle": vehicle,
            "engine": engine,
            "color": color
        }
