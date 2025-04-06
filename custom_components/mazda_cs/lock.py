"""Platform for Mazda lock integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MazdaEntity
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN
from .api_lock import RequestPriority, get_account_lock


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lock platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    account_email = config_entry.data[CONF_EMAIL]

    entities = []

    for index, _ in enumerate(coordinator.data):
        entities.append(MazdaLock(client, coordinator, index, account_email))

    async_add_entities(entities)


class MazdaLock(MazdaEntity, LockEntity):
    """Class for the lock."""

    _attr_translation_key = "lock"

    def __init__(self, client, coordinator, index, account_email) -> None:
        """Initialize Mazda lock."""
        super().__init__(client, coordinator, index)
        self.account_email = account_email
        self._attr_unique_id = self.vin

    @property
    def is_locked(self) -> bool | None:
        """Return true if lock is locked."""
        return self.client.get_assumed_lock_state(self.vehicle_id)

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the vehicle doors."""
        # Get the account lock
        account_lock = get_account_lock(self.account_email)
        
        # Use the lock with COMMAND priority (highest)
        async with account_lock.acquire_context(
            RequestPriority.COMMAND,
            f"lock_doors_{self.vehicle_id}"
        ):
            await self.client.lock_doors(self.vehicle_id)

        self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle doors."""
        # Get the account lock
        account_lock = get_account_lock(self.account_email)
        
        # Use the lock with COMMAND priority (highest)
        async with account_lock.acquire_context(
            RequestPriority.COMMAND,
            f"unlock_doors_{self.vehicle_id}"
        ):
            await self.client.unlock_doors(self.vehicle_id)

        self.async_write_ha_state()