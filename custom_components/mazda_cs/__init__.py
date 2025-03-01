"""The Mazda Connected Services integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
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
    CONF_OPTIONS,
    CONF_REFRESH_INTERVAL,
    CONF_VEHICLE_INTERVAL,
    CONF_ENDPOINT_INTERVAL,
    CONF_HEALTH_REPORT_INTERVAL,
    CONF_HEALTH_VEHICLE_INTERVAL,
    CONF_HEALTH_TIMEOUT,
    CONF_DEBUG_MODE,
    CONF_LOG_RESPONSES,
    CONF_TESTING_MODE,
    CONF_ENABLE_METRICS,
    CONF_DISCOVERY_MODE,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_HEALTH_COORDINATOR,
    DATA_EMAIL,
    DATA_PASSWORD,
    DATA_REGION,
    DATA_VEHICLES,
    DOMAIN,
    DEFAULT_REFRESH_INTERVAL,
    DEFAULT_VEHICLE_INTERVAL,
    DEFAULT_ENDPOINT_INTERVAL,
    DEFAULT_HEALTH_REPORT_INTERVAL,
    DEFAULT_HEALTH_VEHICLE_INTERVAL,
    DEFAULT_HEALTH_TIMEOUT,
)
from .pymazda.client import Client as MazdaAPI
from .pymazda.exceptions import (
    MazdaAccountLockedException,
    MazdaAPIEncryptionException,
    MazdaAuthenticationException,
    MazdaException,
    MazdaTokenExpiredException,
)

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_MAX_SIZE = 5 * 1024 * 1024  # 5MB
LOG_BACKUP_COUNT = 3

_LOGGER = logging.getLogger(__name__)
mazda_logger = logging.getLogger('custom_components.mazda_cs')
handler = RotatingFileHandler(
    'mazda_integration.log',
    maxBytes=LOG_MAX_SIZE,
    backupCount=LOG_BACKUP_COUNT
)
handler.setFormatter(logging.Formatter(LOG_FORMAT))
mazda_logger.addHandler(handler)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def with_timeout(task_or_factory, timeout_seconds=30, retry_on_cancel=True):
    """Run an async task with a timeout.
    
    Args:
        task_or_factory: Either a coroutine or a factory function that returns a new coroutine
        timeout_seconds: Maximum time to wait for task completion
        retry_on_cancel: Whether to retry if the task is cancelled
    """
    is_factory = callable(task_or_factory) and not asyncio.iscoroutine(task_or_factory)
    
    try:
        async with asyncio.timeout(timeout_seconds):
            try:
                if is_factory:
                    # If it's a factory function, call it to get a coroutine
                    task = task_or_factory()
                else:
                    # Otherwise, use the provided coroutine directly
                    task = task_or_factory
                return await task
            except asyncio.CancelledError:
                if not retry_on_cancel:
                    raise
                
                _LOGGER.warning("Task was cancelled, will retry once")
                # Give a short pause and retry once
                await asyncio.sleep(1)
                
                if is_factory:
                    # Create a new coroutine using the factory
                    new_task = task_or_factory()
                    return await new_task
                else:
                    # Can't retry a cancelled coroutine
                    _LOGGER.error("Cannot retry a cancelled coroutine that wasn't created from a factory function")
                    raise
    except asyncio.TimeoutError:
        _LOGGER.error("Timeout after %s seconds. Consider increasing the timeout in the integration options.", timeout_seconds)
        raise


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mazda Connected Services from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    mazda_logger = logging.getLogger("pymazda")

    # Set up and apply configuration options
    if CONF_DEBUG_MODE in entry.options and entry.options[CONF_DEBUG_MODE]:
        _LOGGER.setLevel(logging.DEBUG)
        mazda_logger.setLevel(logging.DEBUG)
        _LOGGER.debug("Debug logging enabled for Mazda integration")
    
    refresh_interval = entry.options.get(
        CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL // 60
    ) * 60  # Convert minutes to seconds
    
    # Get health report interval in minutes
    health_report_minutes = entry.options.get(
        CONF_HEALTH_REPORT_INTERVAL, DEFAULT_HEALTH_REPORT_INTERVAL
    )
    # Convert minutes to seconds for actual usage
    health_report_interval = health_report_minutes * 60
    
    _LOGGER.debug(
        "Health report interval set to %d minutes (%d seconds)",
        health_report_minutes,
        health_report_interval
    )
    
    vehicle_interval = entry.options.get(CONF_VEHICLE_INTERVAL, DEFAULT_VEHICLE_INTERVAL)
    endpoint_interval = entry.options.get(CONF_ENDPOINT_INTERVAL, DEFAULT_ENDPOINT_INTERVAL)
    health_vehicle_interval = entry.options.get(
        CONF_HEALTH_VEHICLE_INTERVAL, DEFAULT_HEALTH_VEHICLE_INTERVAL
    )
    health_timeout = entry.options.get(CONF_HEALTH_TIMEOUT, DEFAULT_HEALTH_TIMEOUT)
    
    # Enable testing mode if selected
    if CONF_TESTING_MODE in entry.options and entry.options[CONF_TESTING_MODE]:
        _LOGGER.warning("TESTING MODE ENABLED - using accelerated update intervals")
        if refresh_interval > 300:  # 5 minutes in seconds
            refresh_interval = 300
            _LOGGER.info("Testing mode: Using 5-minute status refresh interval")
        
        if health_report_interval > 900:  # 15 minutes in seconds
            health_report_interval = 900
            health_report_minutes = 15  # Update minutes to match seconds
            _LOGGER.info("Testing mode: Using 15-minute health report interval")
    
    # Enable API response logging if selected
    log_api_responses = entry.options.get(CONF_LOG_RESPONSES, False)
    if log_api_responses:
        _LOGGER.warning(
            "API response logging enabled - this may expose sensitive data in logs"
        )
    
    # Setup performance metrics tracking if enabled
    track_performance = entry.options.get(CONF_ENABLE_METRICS, False)
    perf_metrics = {} if track_performance else None
    
    _LOGGER.debug(
        "Using configuration: refresh=%ds, vehicle=%ds, endpoint=%ds, health=%ds, health_vehicle=%ds, health_timeout=%ds",
        refresh_interval,
        vehicle_interval,
        endpoint_interval,
        health_report_interval,
        health_vehicle_interval,
        health_timeout
    )

    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    region = entry.data[CONF_REGION]

    websession = aiohttp_client.async_get_clientsession(hass)
    client = MazdaAPI(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        region=entry.data[CONF_REGION],
        websession=websession,
        vehicle_interval=vehicle_interval,
        endpoint_interval=endpoint_interval,
        log_api_responses=log_api_responses,
        performance_metrics=perf_metrics,
    )

    try:
        await client.validate_credentials()
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

    services = {
        "lock_doors": "door_lock",
        "unlock_doors": "door_unlock",
        "engine_start": "engine_start",
        "engine_stop": "engine_stop",
        "hazard_lights": "light_on",
        "send_poi": None,  # Special case, handled separately
        "check_command_status": None,  # New service to check command status
    }

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

    async def handle_check_command_status(service_call):
        """Check the status of a previously executed command."""
        device_id = service_call.data["device_id"]
        visit_no = service_call.data["visit_no"]
        
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        
        if not device:
            raise HomeAssistantError(f"Device {device_id} not found")
            
        # Get the VIN from the device identifier
        vin = None
        for identifier in device.identifiers:
            if identifier[0] == DOMAIN:
                vin = identifier[1]
                break
                
        if not vin:
            raise HomeAssistantError(f"Device {device_id} is not a Mazda vehicle")
            
        # Find the vehicle and client
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
            
        try:
            status = await api_client.get_command_status(vehicle_id, visit_no)
            _LOGGER.info(f"Command status for visit_no {visit_no}: {status}")
            return {"status": status}
        except Exception as ex:
            _LOGGER.error(f"Error checking command status: {ex}")
            raise HomeAssistantError(f"Failed to check command status: {ex}") from ex

    service_schema_check_command_status = vol.Schema(
        {
            vol.Required("device_id"): vol.All(cv.string, validate_mazda_device_id),
            vol.Required("visit_no"): cv.string,
        }
    )

    class MazdaVehicleUpdateCoordinator(DataUpdateCoordinator):
        """Class to manage fetching Mazda data."""

        def __init__(
            self,
            hass: HomeAssistant,
            client: MazdaAPI,
            config_entry: ConfigEntry,
        ) -> None:
            """Initialize coordinator with config and client."""
            self.client = client
            self.config_entry = config_entry
            
            refresh_minutes = config_entry.options.get(
                CONF_REFRESH_INTERVAL, 
                config_entry.data.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL)
            )
            refresh_seconds = int(refresh_minutes * 60)
            
            # Calculate time between vehicle API calls to avoid rate limits
            self.vehicle_interval = config_entry.options.get(
                CONF_VEHICLE_INTERVAL,
                config_entry.data.get(CONF_VEHICLE_INTERVAL, DEFAULT_VEHICLE_INTERVAL)
            )
            
            # Small interval between consecutive API endpoints
            self.endpoint_interval = config_entry.options.get(
                CONF_ENDPOINT_INTERVAL,
                config_entry.data.get(CONF_ENDPOINT_INTERVAL, DEFAULT_ENDPOINT_INTERVAL)
            )

            super().__init__(
                hass,
                _LOGGER,
                name=f"{DOMAIN}_vehicle_status",
                update_interval=timedelta(seconds=refresh_seconds),
            )
            
            _LOGGER.info(
                "Vehicle coordinator initialized with update interval: %.1f minutes (%d seconds), "
                "vehicle interval: %d seconds, endpoint interval: %d seconds", 
                refresh_minutes, 
                refresh_seconds, 
                self.vehicle_interval,
                self.endpoint_interval
            )
            
            # Initialize with empty list
            self.data = []

        async def _async_update_data(self):
            """Fetch data from Mazda API with rate limiting."""
            try:
                vehicles = await with_timeout(
                    lambda: self.client.get_vehicles(),
                    timeout_seconds=60
                )
                _LOGGER.debug("Initial vehicles data: %s", vehicles)
                
                updated_vehicles = []
                vehicle_count = len(vehicles)
                
                for index, vehicle in enumerate(vehicles):
                    # Add inter-vehicle delay after first vehicle
                    if index > 0 and self.vehicle_interval > 0:
                        _LOGGER.debug("Waiting %.1fs between vehicles", self.vehicle_interval)
                        await asyncio.sleep(self.vehicle_interval)
                    
                    try:
                        vin = vehicle["vin"]
                        _LOGGER.debug("Processing vehicle %d/%d: VIN %s", 
                                    index+1, vehicle_count, vin)
                        
                        # Add status with endpoint delay and extended timeout
                        try:
                            vehicle["status"] = await with_timeout(
                                lambda: self.client.get_vehicle_status(vehicle["id"]),
                                timeout_seconds=45
                            )
                            if self.endpoint_interval > 0:
                                await asyncio.sleep(self.endpoint_interval)
                        except Exception as status_ex:
                            _LOGGER.error("Failed to get status for VIN %s: %s", vin, status_ex)
                            vehicle["status"] = None
                        
                        # EV-specific endpoints
                        if vehicle.get("isElectric"):
                            try:
                                vehicle["evStatus"] = await with_timeout(
                                    lambda: self.client.get_ev_vehicle_status(vehicle["id"]),
                                    timeout_seconds=45
                                )
                                if self.endpoint_interval > 0:
                                    await asyncio.sleep(self.endpoint_interval)
                            except Exception as ev_ex:
                                _LOGGER.error("Failed to get EV status for VIN %s: %s", vin, ev_ex)
                                vehicle["evStatus"] = None
                        
                        updated_vehicles.append(vehicle)
                        _LOGGER.debug("Completed vehicle %s", vin)
                    
                    except Exception as ex:
                        _LOGGER.error("Error processing VIN %s: %s", vin, ex)
                        continue

                if not updated_vehicles:
                    raise UpdateFailed("All vehicle updates failed")
                
                self.data = updated_vehicles
                return self.data
            
            except MazdaAuthenticationException as ex:
                raise ConfigEntryAuthFailed("Session expired") from ex
            except Exception as ex:
                _LOGGER.error("Failed to update data: %s", ex)
                raise UpdateFailed(f"Error communicating with API: {ex}") from ex

    class MazdaHealthUpdateCoordinator(DataUpdateCoordinator):
        def __init__(
            self,
            hass: HomeAssistant,
            client: MazdaAPI,
            config_entry: ConfigEntry,
        ) -> None:
            self.client = client
            self.config_entry = config_entry
            self.hass = hass
            
            # Get health report interval in minutes, then convert to seconds for the coordinator
            health_minutes = config_entry.options.get(
                CONF_HEALTH_REPORT_INTERVAL,
                config_entry.data.get(CONF_HEALTH_REPORT_INTERVAL, DEFAULT_HEALTH_REPORT_INTERVAL)
            )
            # Convert minutes to seconds for update interval
            update_interval_seconds = int(health_minutes * 60)
            
            # Get vehicle interval for health reports
            vehicle_interval_seconds = config_entry.options.get(
                CONF_HEALTH_VEHICLE_INTERVAL,
                config_entry.data.get(CONF_HEALTH_VEHICLE_INTERVAL, DEFAULT_HEALTH_VEHICLE_INTERVAL)
            )
            
            # Get health timeout
            health_timeout_seconds = config_entry.options.get(
                CONF_HEALTH_TIMEOUT,
                config_entry.data.get(CONF_HEALTH_TIMEOUT, DEFAULT_HEALTH_TIMEOUT)
            )
            
            # Store for use during updates
            self.vehicle_interval = vehicle_interval_seconds
            self.endpoint_interval = config_entry.options.get(
                CONF_ENDPOINT_INTERVAL,
                config_entry.data.get(CONF_ENDPOINT_INTERVAL, DEFAULT_ENDPOINT_INTERVAL)
            )
            self.health_timeout = health_timeout_seconds
            
            # Get debug and discovery mode settings
            self.debug_mode = config_entry.options.get(
                CONF_DEBUG_MODE,
                config_entry.data.get(CONF_DEBUG_MODE, False)
            )
            
            self.discovery_mode = config_entry.options.get(
                CONF_DISCOVERY_MODE,
                config_entry.data.get(CONF_DISCOVERY_MODE, False)
            )
            
            if self.discovery_mode:
                _LOGGER.warning("Discovery Mode is enabled - all health report sensors will be logged")
            
            super().__init__(
                hass,
                _LOGGER,
                name="Mazda Health Report",
                update_interval=timedelta(seconds=update_interval_seconds),
            )
            
            _LOGGER.debug(
                "Health coordinator update interval set to %d minutes (%d seconds)",
                health_minutes,
                update_interval_seconds
            )

        async def _async_update_data(self):
            """Fetch and process health data for all vehicles."""
            try:
                # Use a dictionary keyed by VIN to store health reports
                results = {}
                
                # Get the list of vehicles from hass.data
                vehicles = self.hass.data[DOMAIN][self.config_entry.entry_id][DATA_VEHICLES]
                _LOGGER.debug("Processing health reports for %d vehicles", len(vehicles))
                
                for index, vehicle in enumerate(vehicles):
                    vehicle_id = vehicle["id"]
                    vin = vehicle["vin"]
                    nickname = vehicle.get("nickname", "")
                    model = f"{vehicle.get('modelYear', '')} {vehicle.get('carlineName', '')}"
                    
                    # Add delay between vehicles to prevent API rate limiting
                    if index > 0 and self.vehicle_interval > 0:
                        _LOGGER.debug("Waiting %d seconds before processing next vehicle", self.vehicle_interval)
                        await asyncio.sleep(self.vehicle_interval)
                    
                    try:
                        _LOGGER.debug("Fetching health report for %s: %s (VIN: %s)", 
                                      model, nickname, vin)
                        
                        # Fetch health report with timeout
                        raw_data = await with_timeout(
                            lambda: self.client.get_health_report(vehicle_id),
                            timeout_seconds=self.health_timeout
                        )
                        
                        if raw_data:
                            if self.debug_mode:
                                _LOGGER.debug("Health report data for %s: %s", 
                                            vin, sanitize_sensitive_data(raw_data))
                            
                            # Store result by VIN for sensor access
                            results[vin] = raw_data
                            _LOGGER.info("Successfully fetched health report for %s %s", 
                                        model, nickname)
                        else:
                            _LOGGER.warning("Empty health report received for %s %s", 
                                           model, nickname)
                    
                    except Exception as ex:
                        _LOGGER.warning("Failed to get health report for %s %s: %s", 
                                        model, nickname, ex)
                
                if not results:
                    _LOGGER.warning("No health report data could be fetched for any vehicle")
                
                return results
                
            except Exception as error:
                _LOGGER.error("Error in health report coordinator: %s", error)
                raise UpdateFailed(f"Error fetching health reports: {error}") from error

    coordinator = MazdaVehicleUpdateCoordinator(hass, client, entry)
    
    health_coordinator = MazdaHealthUpdateCoordinator(hass, client, entry)
    
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
        DATA_HEALTH_COORDINATOR: health_coordinator,
        DATA_EMAIL: email,
        DATA_PASSWORD: password,
        DATA_REGION: region,
        DATA_VEHICLES: [],
    }

    # Force refresh coordinators to get initial data
    await coordinator.async_refresh()
    # Remove immediate health report refresh during initialization
    # await health_coordinator.async_refresh()

    # Store vehicle information for use by platform components
    hass.data[DOMAIN][entry.entry_id][DATA_VEHICLES] = coordinator.data
    
    # Create device registry
    dev_reg = dr.async_get(hass)
    for vehicle in coordinator.data:
        _LOGGER.debug(f"Registering device for vehicle VIN {vehicle['vin']}")
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, vehicle["vin"])},
            manufacturer="Mazda",
            model=f"{vehicle['modelYear']} {vehicle['carlineName']}",
            name=vehicle.get("nickname", f"{vehicle['modelYear']} {vehicle['carlineName']}"),
        )

    # Forward the setup to platform modules
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    hass.services.async_register(
        DOMAIN, "send_poi", async_handle_service_call, schema=service_schema_send_poi
    )
    
    # Register the command status check service
    hass.services.async_register(
        DOMAIN, "check_command_status", handle_check_command_status, 
        schema=service_schema_check_command_status
    )

    # Schedule health report update after initialization is complete
    # This makes the health report non-blocking during startup
    async def start_health_reports(now=None):
        """Start the health report coordinator after initialization."""
        _LOGGER.info("Starting initial health report fetch")
        await health_coordinator.async_refresh()

    # Schedule the initial health report fetch for 15 seconds after startup
    # This allows time for the integration to fully initialize first
    health_report_delay = 15  # seconds
    hass.loop.call_later(
        health_report_delay,
        lambda: hass.async_create_task(start_health_reports())
    )
    _LOGGER.info(f"Scheduled initial health report to start in {health_report_delay} seconds")

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Display performance metrics before unloading if enabled
    if entry.options.get(CONF_ENABLE_METRICS, False) and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        if DATA_CLIENT in hass.data[DOMAIN][entry.entry_id]:
            client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
            if hasattr(client, "performance_metrics") and client.performance_metrics:
                metrics = client.performance_metrics
                _LOGGER.info("Mazda API Performance Metrics:")
                for endpoint, data in metrics.items():
                    if "count" in data and data["count"] > 0:
                        avg_time = data.get("total_time", 0) / data["count"]
                        _LOGGER.info(
                            "Endpoint %s: %d calls, avg %.2f sec, min %.2f sec, max %.2f sec",
                            endpoint,
                            data["count"],
                            avg_time,
                            data.get("min_time", 0),
                            data.get("max_time", 0),
                        )
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Only remove services if it is the last config entry
    if len(hass.data[DOMAIN]) == 1:
        hass.services.async_remove(DOMAIN, "send_poi")
        hass.services.async_remove(DOMAIN, "check_command_status")

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
        
        _LOGGER.debug(
            "Creating entity for VIN %s - Nickname: %s | Model: %s %s",
            self.vin,
            self.data.get("nickname", "None"),
            self.data.get("modelYear", "Unknown"),
            self.data.get("carlineName", "Unknown")
        )

        # Ensure proper device linkage
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.vin)},
            manufacturer="Mazda",
            model=f"{self.data.get('modelYear', '')} {self.data.get('carlineName', '')}",
            name=self.vehicle_name,
            hw_version=self.data.get("hdopVersion", ""),
            sw_version=self.data.get("swVersion", ""),
            configuration_url="https://www.mazdausa.com/owners/my-mazda-connected-services",
        )

    @property
    def data(self):
        """Shortcut to access coordinator data for the entity."""
        return self.coordinator.data[self.index]

    @property
    def vehicle_name(self):
        """Return the vehicle name, to be used as a prefix for names of other entities."""
        nickname = self.data.get("nickname")
        fallback = f"{self.data['modelYear']} {self.data['carlineName']}"
        
        if nickname and len(nickname) > 0:
            _LOGGER.debug(
                "Using nickname '%s' for VIN %s",
                nickname,
                self.vin
            )
            return nickname
            
        _LOGGER.debug(
            "Using fallback name for VIN %s: %s",
            self.vin,
            fallback
        )
        return fallback