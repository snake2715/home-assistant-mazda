"""Health data coordinator for Mazda Connected Services."""
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api_lock import RequestPriority, get_account_lock
from .const import DOMAIN
from .pymazda.client import Client as MazdaAPI

_LOGGER = logging.getLogger(__name__)

class MazdaHealthUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Mazda health data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MazdaAPI,
        vehicle_id: str,
        update_interval: int,
        account_email: str,
    ):
        """Initialize the health data update coordinator."""
        self.client = client
        self.vehicle_id = vehicle_id
        self.account_email = account_email
        self.vehicle = None  # Will be populated during first update
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_health_{vehicle_id}",
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            # Initialize the health report structure
            health_report = {}
            
            # Get the account lock
            account_lock = get_account_lock(self.account_email)
            
            # Use the lock with HEALTH_REPORT priority (lowest)
            async with account_lock.acquire_context(
                RequestPriority.HEALTH_REPORT,
                f"health_refresh_{self.vehicle_id}"
            ):
                try:
                    # Get the full vehicle details if we don't have them yet
                    if not self.vehicle:
                        try:
                            vehicles = await self.client.get_vehicles()
                            for vehicle in vehicles:
                                if vehicle["id"] == self.vehicle_id:
                                    self.vehicle = vehicle
                                    break
                        except Exception as ex:
                            _LOGGER.warning("Error fetching vehicles: %s", ex)
                    
                    if not self.vehicle:
                        _LOGGER.warning("Vehicle %s not found, using vehicle_id only", self.vehicle_id)
                    
                    # Get vehicle status (this contains all the health data we need)
                    vehicle_status = await self.client.get_vehicle_status(self.vehicle_id)
                    _LOGGER.debug("Got vehicle status for health data: %s", self.vehicle_id)
                    
                    # Debug the entire vehicle status response structure
                    _LOGGER.debug("Full vehicle status response structure: %s", list(vehicle_status.keys()))
                    
                    # Store the full vehicle status in the health report for direct access
                    health_report["vehicle_status"] = vehicle_status
                    
                    # Get the raw API response which now should be included in the vehicle_status
                    raw_response = vehicle_status.get("raw_response")
                    
                    # Extract remoteInfos from the raw response if available
                    if raw_response and "remoteInfos" in raw_response:
                        _LOGGER.debug("Found remoteInfos in raw API response")
                        health_report["remoteInfos"] = raw_response["remoteInfos"]
                        
                        # Process each remote info item
                        for remote_info in raw_response["remoteInfos"]:
                            # Extract Drive Information (Odometer)
                            if "DriveInformation" in remote_info:
                                health_report["DriveInformation"] = remote_info["DriveInformation"]
                                if "OdoDispValue" in remote_info["DriveInformation"]:
                                    health_report["OdoDispValue"] = remote_info["DriveInformation"]["OdoDispValue"]
                                    _LOGGER.debug("Extracted Odometer: %s", remote_info["DriveInformation"]["OdoDispValue"])
                                if "OdoDispValueMile" in remote_info["DriveInformation"]:
                                    health_report["OdoDispValueMile"] = remote_info["DriveInformation"]["OdoDispValueMile"]
                                    _LOGGER.debug("Extracted Odometer (Miles): %s", remote_info["DriveInformation"]["OdoDispValueMile"])
                            
                            # Extract TPMS Information
                            if "TPMSInformation" in remote_info:
                                health_report["TPMSInformation"] = remote_info["TPMSInformation"]
                                _LOGGER.debug("Extracted TPMS Information: %s", remote_info["TPMSInformation"])
                                
                                # Extract individual tire pressures for all models
                                tpms_info = remote_info["TPMSInformation"]
                                for key in ["FLTPrsDispPsi", "FRTPrsDispPsi", "RLTPrsDispPsi", "RRTPrsDispPsi", "TPMSStatus", "TPMSSystemFlt"]:
                                    if key in tpms_info:
                                        health_report[f"TPMSInformation.{key}"] = tpms_info[key]
                                        _LOGGER.debug("Extracted %s: %s", key, tpms_info[key])
                            
                            # Extract Oil Maintenance Information
                            if "OilMntInformation" in remote_info:
                                health_report["OilMntInformation"] = remote_info["OilMntInformation"]
                                _LOGGER.debug("Extracted Oil Maintenance Information: %s", remote_info["OilMntInformation"])
                                
                                # Extract specific oil maintenance fields for direct access
                                oil_info = remote_info["OilMntInformation"]
                                for key in ["RemOilDistK", "RemOilDistMile", "OilDeteriorateWarning", "OilLevelWarning"]:
                                    if key in oil_info:
                                        health_report[f"OilMntInformation.{key}"] = oil_info[key]
                                        _LOGGER.debug("Extracted %s: %s", key, oil_info[key])
                            
                            # Extract Regular Maintenance Information
                            if "RegularMntInformation" in remote_info:
                                health_report["RegularMntInformation"] = remote_info["RegularMntInformation"]
                                _LOGGER.debug("Extracted Regular Maintenance Information: %s", remote_info["RegularMntInformation"])
                                
                                # Extract specific maintenance fields for direct access
                                mnt_info = remote_info["RegularMntInformation"]
                                for key in ["MntSetDistKm", "MntSetDistMile"]:
                                    if key in mnt_info:
                                        health_report[f"RegularMntInformation.{key}"] = mnt_info[key]
                                        _LOGGER.debug("Extracted %s: %s", key, mnt_info[key])
                            
                            # Extract Occurrence Date for Health Report Date
                            if "OccurrenceDate" in remote_info:
                                health_report["OccurrenceDate"] = remote_info["OccurrenceDate"]
                                _LOGGER.debug("Extracted Occurrence Date: %s", remote_info["OccurrenceDate"])
                    else:
                        # If we can't access the raw response, try to extract data from the processed vehicle_status
                        _LOGGER.warning("Could not access raw API response with remoteInfos, falling back to processed vehicle_status")
                        
                        # Try to extract odometer from the processed vehicle_status
                        if "odometerKm" in vehicle_status:
                            health_report["OdoDispValue"] = vehicle_status["odometerKm"]
                            _LOGGER.debug("Extracted Odometer from processed data: %s", vehicle_status["odometerKm"])
                        
                        # Try to extract tire pressure from the processed vehicle_status
                        if "tirePressure" in vehicle_status and vehicle_status["tirePressure"]:
                            tire_pressure = vehicle_status["tirePressure"]
                            health_report["TPMSInformation"] = tire_pressure
                            _LOGGER.debug("Extracted TPMS Information from processed data: %s", tire_pressure)
                            
                            # Map tire pressure fields if they exist
                            tire_mapping = {
                                "frontLeft": "FLTPrsDispPsi",
                                "frontRight": "FRTPrsDispPsi",
                                "rearLeft": "RLTPrsDispPsi",
                                "rearRight": "RRTPrsDispPsi"
                            }
                            
                            for processed_key, raw_key in tire_mapping.items():
                                if processed_key in tire_pressure and tire_pressure[processed_key]:
                                    health_report[f"TPMSInformation.{raw_key}"] = tire_pressure[processed_key]
                                    _LOGGER.debug("Extracted %s from processed data: %s", raw_key, tire_pressure[processed_key])
                    
                    # Log the final health report structure
                    _LOGGER.debug("Final health report keys: %s", list(health_report.keys()))
                    
                except Exception as ex:
                    _LOGGER.error("Error fetching vehicle status for health data: %s", ex)
                    # Return an empty health report instead of raising an exception
                    # This allows sensors to recover more gracefully
                    return {
                        "health_report": {}
                    }
                
                return {
                    "health_report": health_report
                }
                
        except Exception as ex:
            _LOGGER.error("Error updating health data: %s", ex)
            # Return an empty health report instead of raising an exception
            return {
                "health_report": {}
            }
