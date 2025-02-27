"""Config flow for Mazda Connected Services integration."""
from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client

from . import MazdaAccountLockedException, MazdaAPI, MazdaAuthenticationException
from .const import (
    DOMAIN,
    MAZDA_REGIONS,
    CONF_REFRESH_INTERVAL,
    CONF_VEHICLE_INTERVAL,
    CONF_ENDPOINT_INTERVAL,
    CONF_HEALTH_REPORT_INTERVAL,
    CONF_HEALTH_VEHICLE_INTERVAL,
    CONF_DEBUG_MODE,
    CONF_LOG_RESPONSES,
    CONF_ENABLE_METRICS,
    CONF_TESTING_MODE,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION): vol.In(MAZDA_REGIONS),
        vol.Optional(
            CONF_REFRESH_INTERVAL,
            default=15,
            description={
                "suggested_value": 15,
                "name": "Status Update Frequency (minutes)",
                "description": "How often to update vehicle status (5-1440 min)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
        vol.Optional(
            CONF_VEHICLE_INTERVAL,
            default=2,
            description={
                "suggested_value": 2,
                "name": "Delay Between Vehicles (seconds)",
                "description": "Delay between processing each vehicle (0-60 sec)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
        vol.Optional(
            CONF_ENDPOINT_INTERVAL,
            default=1,
            description={
                "suggested_value": 1,
                "name": "API Throttling Delay (seconds)",
                "description": "Delay between API calls for same vehicle (0-30 sec)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
        vol.Optional(
            CONF_HEALTH_REPORT_INTERVAL,
            default=60,
            description={
                "suggested_value": 60,
                "name": "Health Report Frequency (minutes)",
                "description": "How often to retrieve health reports (5-1440 minutes)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
        vol.Optional(
            CONF_HEALTH_VEHICLE_INTERVAL,
            default=30,
            description={
                "suggested_value": 30,
                "name": "Health Report Vehicle Delay (seconds)",
                "description": "Delay between health report calls (5-300 sec)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(
            CONF_REFRESH_INTERVAL,
            default=15,
            description={
                "suggested_value": 15,
                "name": "Status Update Frequency",
                "description": "How often to update vehicle status (5-1440 minutes)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
        vol.Optional(
            CONF_HEALTH_REPORT_INTERVAL,
            default=60,
            description={
                "suggested_value": 60,
                "name": "Health Report Frequency",
                "description": "How often to retrieve health reports (5-1440 minutes)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
        vol.Optional(
            CONF_VEHICLE_INTERVAL,
            default=2,
            description={
                "suggested_value": 2,
                "name": "Vehicle Processing Delay",
                "description": "Time between processing each vehicle (0-60 seconds)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
        vol.Optional(
            CONF_ENDPOINT_INTERVAL,
            default=1,
            description={
                "suggested_value": 1,
                "name": "API Call Delay",
                "description": "Time between API calls for same vehicle (0-30 seconds)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
        vol.Optional(
            CONF_HEALTH_VEHICLE_INTERVAL,
            default=30,
            description={
                "suggested_value": 30,
                "name": "Health Report API Delay",
                "description": "Time between health report API calls (5-300 seconds)"
            },
        ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
        vol.Optional(
            CONF_DEBUG_MODE,
            default=False,
            description={
                "suggested_value": False,
                "name": "Debug Mode",
                "description": "Enable detailed debug logging"
            },
        ): bool,
        vol.Optional(
            CONF_LOG_RESPONSES,
            default=False,
            description={
                "suggested_value": False,
                "name": "Log API Responses",
                "description": "Log full API responses (WARNING: may include sensitive data)"
            },
        ): bool,
        vol.Optional(
            CONF_TESTING_MODE,
            default=False,
            description={
                "suggested_value": False,
                "name": "Testing Mode",
                "description": "Enables more frequent updates for testing"
            },
        ): bool,
        vol.Optional(
            CONF_ENABLE_METRICS,
            default=False,
            description={
                "suggested_value": False,
                "name": "Performance Metrics",
                "description": "Track API performance metrics"
            },
        ): bool,
    }
)


class MazdaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mazda Connected Services."""

    VERSION = 1

    def __init__(self):
        """Start the mazda config flow."""
        self._reauth_entry = None
        self._email = None
        self._region = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._region = user_input[CONF_REGION]
            unique_id = user_input[CONF_EMAIL].lower()
            await self.async_set_unique_id(unique_id)
            if not self._reauth_entry:
                self._abort_if_unique_id_configured()
            websession = aiohttp_client.async_get_clientsession(self.hass)
            mazda_client = MazdaAPI(
                user_input[CONF_EMAIL],
                user_input[CONF_PASSWORD],
                user_input[CONF_REGION],
                websession,
            )

            try:
                await mazda_client.validate_credentials()
            except MazdaAuthenticationException:
                errors["base"] = "invalid_auth"
            except MazdaAccountLockedException:
                errors["base"] = "account_locked"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception as ex:  # pylint: disable=broad-except
                errors["base"] = "unknown"
                _LOGGER.exception(
                    "Unknown error occurred during Mazda login request: %s", ex
                )
            else:
                if not self._reauth_entry:
                    return self.async_create_entry(
                        title=user_input[CONF_EMAIL], data=user_input
                    )
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry, data=user_input, unique_id=unique_id
                )
                # Reload the config entry otherwise devices will remain unavailable
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=self._email): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_REGION, default=self._region): vol.In(
                        MAZDA_REGIONS
                    ),
                    vol.Optional(
                        CONF_REFRESH_INTERVAL,
                        default=15,
                        description={
                            "suggested_value": 15,
                            "name": "Status Update Frequency (minutes)",
                            "description": "How often to update vehicle status (5-1440 min)"
                        },
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                    vol.Optional(
                        CONF_VEHICLE_INTERVAL,
                        default=2,
                        description={
                            "suggested_value": 2,
                            "name": "Delay Between Vehicles (seconds)",
                            "description": "Delay between processing each vehicle (0-60 sec)"
                        },
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                    vol.Optional(
                        CONF_ENDPOINT_INTERVAL,
                        default=1,
                        description={
                            "suggested_value": 1,
                            "name": "API Throttling Delay (seconds)",
                            "description": "Delay between API calls for same vehicle (0-30 sec)"
                        },
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=30)),
                    vol.Optional(
                        CONF_HEALTH_REPORT_INTERVAL,
                        default=60,
                        description={
                            "suggested_value": 60,
                            "name": "Health Report Frequency (minutes)",
                            "description": "How often to retrieve health reports (5-1440 minutes)"
                        },
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                    vol.Optional(
                        CONF_HEALTH_VEHICLE_INTERVAL,
                        default=30,
                        description={
                            "suggested_value": 30,
                            "name": "Health Report Vehicle Delay (seconds)",
                            "description": "Delay between health report calls (5-300 sec)"
                        },
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Perform reauth if the user credentials have changed."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._email = entry_data[CONF_EMAIL]
        self._region = entry_data[CONF_REGION]
        return await self.async_step_user()

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            if CONF_REFRESH_INTERVAL in user_input:
                _LOGGER.debug(
                    "Converting refresh interval from %d minutes to seconds",
                    user_input[CONF_REFRESH_INTERVAL]
                )

            if CONF_HEALTH_REPORT_INTERVAL in user_input:
                _LOGGER.debug(
                    "Converting health report interval from %d minutes to seconds",
                    user_input[CONF_HEALTH_REPORT_INTERVAL]
                )

            if user_input.get(CONF_TESTING_MODE, False):
                _LOGGER.warning(
                    "TESTING MODE ENABLED: This will cause more frequent API calls and is not recommended for production use"
                )
                
                if CONF_REFRESH_INTERVAL in user_input and user_input[CONF_REFRESH_INTERVAL] > 10:
                    user_input[CONF_REFRESH_INTERVAL] = 5
                    _LOGGER.info("Testing mode: Setting refresh interval to 5 minutes")
                
                if CONF_HEALTH_REPORT_INTERVAL in user_input and user_input[CONF_HEALTH_REPORT_INTERVAL] > 15:
                    user_input[CONF_HEALTH_REPORT_INTERVAL] = 15
                    _LOGGER.info("Testing mode: Setting health report interval to 15 minutes")
                
                if CONF_VEHICLE_INTERVAL in user_input and user_input[CONF_VEHICLE_INTERVAL] > 2:
                    user_input[CONF_VEHICLE_INTERVAL] = 1
                    _LOGGER.info("Testing mode: Setting vehicle interval to 1 second")
                
                if CONF_ENDPOINT_INTERVAL in user_input and user_input[CONF_ENDPOINT_INTERVAL] > 1:
                    user_input[CONF_ENDPOINT_INTERVAL] = 0
                    _LOGGER.info("Testing mode: Setting endpoint interval to 0 seconds")
            
            if user_input.get(CONF_DEBUG_MODE, False):
                _LOGGER.setLevel(logging.DEBUG)
                _LOGGER.debug("Debug logging enabled through configuration")
            
            return self.async_create_entry(title="", data=user_input)

        current_config = {**self.config_entry.data, **self.config_entry.options}
        
        defaults = {
            CONF_REFRESH_INTERVAL: current_config.get(CONF_REFRESH_INTERVAL, 15),
            CONF_VEHICLE_INTERVAL: current_config.get(CONF_VEHICLE_INTERVAL, 2),
            CONF_ENDPOINT_INTERVAL: current_config.get(CONF_ENDPOINT_INTERVAL, 1),
            CONF_HEALTH_REPORT_INTERVAL: current_config.get(CONF_HEALTH_REPORT_INTERVAL, 60),
            CONF_HEALTH_VEHICLE_INTERVAL: current_config.get(CONF_HEALTH_VEHICLE_INTERVAL, 30),
            CONF_DEBUG_MODE: current_config.get(CONF_DEBUG_MODE, False),
            CONF_LOG_RESPONSES: current_config.get(CONF_LOG_RESPONSES, False),
            CONF_TESTING_MODE: current_config.get(CONF_TESTING_MODE, False),
            CONF_ENABLE_METRICS: current_config.get(CONF_ENABLE_METRICS, False),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, defaults
            ),
            description_placeholders={
                "name": self.config_entry.title,
                "integration": "Mazda Connected Services",
            },
        )
