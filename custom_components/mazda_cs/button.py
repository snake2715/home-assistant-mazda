"""Platform for Mazda button integration."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
import asyncio
import aiohttp
from typing import Any, Final

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import (
    MazdaAccountLockedException,
    MazdaAPI as MazdaAPIClient,
    MazdaAPIEncryptionException,
    MazdaAuthenticationException,
    MazdaEntity,
    MazdaException,
    MazdaTokenExpiredException,
)
from .const import DATA_CLIENT, DATA_COORDINATOR, DATA_HEALTH_COORDINATOR, DOMAIN
from .pymazda.exceptions import MazdaLoginFailedException

_LOGGER = logging.getLogger(__name__)


async def handle_button_press(
    client: MazdaAPIClient,
    key: str,
    vehicle_id: int,
    coordinator: DataUpdateCoordinator,
) -> None:
    """Handle a press for a Mazda button entity."""
    api_method = getattr(client, key)
    _LOGGER = logging.getLogger(__name__)

    # Number of retries for transient errors
    MAX_RETRIES: Final = 2
    retry_count = 0

    while retry_count <= MAX_RETRIES:
        try:
            await api_method(vehicle_id)
            # If successful, break out of the retry loop
            break
        except (
            MazdaException,
            MazdaAuthenticationException,
            MazdaAccountLockedException,
            MazdaTokenExpiredException,
            MazdaAPIEncryptionException,
            MazdaLoginFailedException,
        ) as ex:
            raise HomeAssistantError(ex) from ex
        except aiohttp.client_exceptions.ServerDisconnectedError as ex:
            if retry_count < MAX_RETRIES:
                _LOGGER.warning(
                    "Server disconnected during %s operation. Retrying... (%d/%d)",
                    key,
                    retry_count + 1,
                    MAX_RETRIES,
                )
                retry_count += 1
                # Add exponential backoff
                await asyncio.sleep(2 ** retry_count)
            else:
                _LOGGER.error(
                    "Server disconnected during %s operation after %d retries. Check your network connection and the Mazda API status.",
                    key,
                    MAX_RETRIES,
                )
                raise HomeAssistantError(f"Failed to {key} after multiple retries: {ex}") from ex
        except (aiohttp.ClientError, asyncio.TimeoutError) as ex:
            if retry_count < MAX_RETRIES:
                _LOGGER.warning(
                    "Connection error during %s operation. Retrying... (%d/%d)",
                    key,
                    retry_count + 1,
                    MAX_RETRIES,
                )
                retry_count += 1
                # Add exponential backoff
                await asyncio.sleep(2 ** retry_count)
            else:
                _LOGGER.error(
                    "Connection error during %s operation after %d retries: %s",
                    key,
                    MAX_RETRIES,
                    str(ex),
                )
                raise HomeAssistantError(f"Connection error during {key} operation: {ex}") from ex


async def handle_refresh_vehicle_status(
    client: MazdaAPIClient,
    key: str,
    vehicle_id: int,
    coordinator: DataUpdateCoordinator,
) -> None:
    """Handle a request to refresh the vehicle status."""
    await handle_button_press(client, key, vehicle_id, coordinator)

    await coordinator.async_request_refresh()


async def handle_refresh_health_report(
    client: MazdaAPIClient,
    key: str,
    vehicle_id: int,
    coordinator: DataUpdateCoordinator,
) -> None:
    """Handle a request to refresh the health report."""
    # Get the current entry ID from the coordinator
    entry_id = None
    for entry_id, entry_data in coordinator.hass.data[DOMAIN].items():
        if DATA_COORDINATOR in entry_data and entry_data[DATA_COORDINATOR] == coordinator:
            break
    
    if not entry_id:
        _LOGGER.error("Could not find config entry ID for coordinator")
        raise HomeAssistantError("Configuration entry not found")
    
    # Get the health coordinator directly from the current entry
    health_coordinator = coordinator.hass.data[DOMAIN][entry_id].get(DATA_HEALTH_COORDINATOR)
    
    if not health_coordinator:
        _LOGGER.error("Health coordinator not found in current config entry")
        raise HomeAssistantError("Health coordinator not available")
    
    try:
        # Try to get the VIN for better logging
        vin = "unknown"
        for vehicle in coordinator.data:
            if vehicle.get("id") == vehicle_id:
                vin = vehicle.get("vin", "unknown")
                break
        
        _LOGGER.info("Triggering manual refresh of health report for vehicle %s (ID: %s)", vin, vehicle_id)
        
        # Request refresh of health data
        await health_coordinator.async_request_refresh()
        _LOGGER.info("Health report refresh completed for vehicle %s", vin)
    except Exception as ex:
        _LOGGER.error("Error refreshing health report: %s", ex)
        raise HomeAssistantError(f"Failed to refresh health report: {ex}") from ex


@dataclass
class MazdaButtonEntityDescription(ButtonEntityDescription):
    """Describes a Mazda button entity."""

    # Function to determine whether the vehicle supports this button,
    # given the coordinator data
    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True

    async_press: Callable[
        [MazdaAPIClient, str, int, DataUpdateCoordinator], Awaitable
    ] = handle_button_press


BUTTON_ENTITIES = [
    MazdaButtonEntityDescription(
        key="start_engine",
        translation_key="start_engine",
        icon="mdi:engine",
        is_supported=lambda data: not data["isElectric"],
    ),
    MazdaButtonEntityDescription(
        key="stop_engine",
        translation_key="stop_engine",
        icon="mdi:engine-off",
        is_supported=lambda data: not data["isElectric"],
    ),
    MazdaButtonEntityDescription(
        key="turn_on_hazard_lights",
        translation_key="turn_on_hazard_lights",
        icon="mdi:hazard-lights",
        is_supported=lambda data: not data["isElectric"],
    ),
    MazdaButtonEntityDescription(
        key="turn_off_hazard_lights",
        translation_key="turn_off_hazard_lights",
        icon="mdi:hazard-lights",
        is_supported=lambda data: not data["isElectric"],
    ),
    MazdaButtonEntityDescription(
        key="refresh_vehicle_status",
        translation_key="refresh_vehicle_status",
        icon="mdi:refresh",
        async_press=handle_refresh_vehicle_status,
    ),
    MazdaButtonEntityDescription(
        key="refresh_health_report",
        translation_key="refresh_health_report",
        icon="mdi:car-wrench",
        async_press=handle_refresh_health_report,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Mazda button platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities = []
    for index, data in enumerate(coordinator.data):
        for description in BUTTON_ENTITIES:
            if description.is_supported(data):
                entities.append(
                    MazdaButtonEntity(
                        client,
                        coordinator,
                        index,
                        description,
                    )
                )

    async_add_entities(entities)


class MazdaButtonEntity(MazdaEntity, ButtonEntity):
    """Representation of a Mazda button."""

    entity_description: MazdaButtonEntityDescription

    def __init__(
        self,
        client: MazdaAPIClient,
        coordinator: DataUpdateCoordinator,
        index: int,
        description: MazdaButtonEntityDescription,
    ) -> None:
        """Initialize Mazda button."""
        super().__init__(client, coordinator, index)
        self.entity_description = description

        self._attr_unique_id = f"{self.vin}_{description.key}"

    async def async_press(self) -> None:
        """Press the button."""
        await self.entity_description.async_press(
            self.client, self.entity_description.key, self.vehicle_id, self.coordinator
        )
