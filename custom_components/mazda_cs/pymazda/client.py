import json
import logging
import time
import asyncio
import random
import datetime
from aiohttp.client_exceptions import ServerDisconnectedError, ClientConnectorError, ClientOSError, ClientResponseError
from aiohttp import ClientError

from .controller import Controller
from .exceptions import MazdaException
from ..priority_lock import RequestPriority

_LOGGER = logging.getLogger(__name__)

class Client:  # noqa: D101
    def __init__(  # noqa: D107
        self, 
        email, 
        password, 
        region, 
        websession=None, 
        use_cached_vehicle_list=False,
        vehicle_interval=2,
        endpoint_interval=1,
        log_api_responses=False,
        performance_metrics=None
    ):
        if email is None or len(email) == 0:
            raise MazdaConfigException("Invalid or missing email address")
        if password is None or len(password) == 0:
            raise MazdaConfigException("Invalid or missing password")

        self.controller = Controller(
            email, 
            password, 
            region, 
            websession,
            log_api_responses=log_api_responses
        )

        self._cached_state = {}
        self._use_cached_vehicle_list = use_cached_vehicle_list
        self._cached_vehicle_list = None
        self._vehicle_delay = vehicle_interval
        self._endpoint_delay = endpoint_interval
        self._log_api_responses = log_api_responses
        self.performance_metrics = performance_metrics
        # Add nickname cache to reduce API calls
        self._nickname_cache = {}
        self._nickname_cache_expiry = {}
        self._nickname_cache_duration = datetime.timedelta(hours=24)  # Cache nicknames for 24 hours

    async def validate_credentials(self):  # noqa: D102
        try:
            await self.controller.login(RequestPriority.USER_COMMAND)
        except (MazdaException, ClientError) as ex:
            _LOGGER.error("Error validating credentials: %s", str(ex))
            raise

    async def test_authentication(self, detailed_diagnostics=True):
        """Test authentication and return diagnostics.
        
        This method attempts to log in and provides detailed information about
        any authentication issues encountered.
        
        Args:
            detailed_diagnostics: Whether to return detailed diagnostic information
            
        Returns:
            dict: Authentication test results including success status and diagnostics
        """
        result = {
            "success": False,
            "message": "",
            "details": {}
        }
        
        try:
            # Try login with expanded error handling
            await self.controller.login(RequestPriority.USER_COMMAND)
            
            # If we got here, login was successful
            result["success"] = True
            result["message"] = "Authentication successful"
            
            if detailed_diagnostics:
                # Include some basic details about the connection
                result["details"]["email_length"] = len(self.controller.connection.email)
                result["details"]["email_has_spaces"] = " " in self.controller.connection.email
                
                # Get vehicles to test token validity
                try:
                    vehicles = await self.get_vehicles()
                    result["details"]["vehicles_found"] = len(vehicles)
                except (MazdaException, ClientError) as ex:
                    result["details"]["vehicle_fetch_error"] = str(ex)
            
        except (MazdaException, ClientError) as ex:
            # Authentication failed
            result["success"] = False
            result["message"] = f"Authentication failed: {str(ex)}"
            
            if detailed_diagnostics:
                # Include diagnostic information
                result["details"]["exception_type"] = type(ex).__name__
                result["details"]["email_length"] = len(self.controller.connection.email)
                result["details"]["email_has_spaces"] = " " in self.controller.connection.email
                
                # Check for common issues
                if " " in self.controller.connection.email:
                    result["details"]["suggestion"] = "Email contains spaces. Try removing spaces and attempt login again."
                elif len(self.controller.connection.password) < 8:
                    result["details"]["suggestion"] = "Password seems too short. Make sure you entered the correct password."
                else:
                    result["details"]["suggestion"] = "Try manually typing your credentials instead of copy-pasting. Check for typos and ensure you're using the correct region."
        
        return result

    async def get_vehicles(self):  # noqa: D102
        """Get information about all Mazda vehicles linked to the account.
        
        Returns:
            list: A list of vehicle information dictionaries
        """
        start_time = time.time() if self.performance_metrics is not None else None
        
        # Use cached vehicle list if enabled and available
        if self._use_cached_vehicle_list and self._cached_vehicle_list is not None:
            return self._cached_vehicle_list
            
        try:
            max_retries = 3
            retry_count = 0
            last_error = None
            
            while retry_count < max_retries:
                try:
                    vec_base_infos_response = await self.controller.get_vec_base_infos(RequestPriority.VEHICLE_STATUS)
                    break  # Success, exit the retry loop
                except (ServerDisconnectedError, ClientConnectorError, ClientOSError) as e:
                    retry_count += 1
                    last_error = e
                    if retry_count >= max_retries:
                        _LOGGER.error("Error getting vehicle list: %s", str(e))
                        raise
                    
                    # Exponential backoff with jitter
                    wait_time = min(2 ** retry_count + (0.1 * random.random()), 30)
                    _LOGGER.warning(
                        "Server connection error while getting vehicle list: %s. "
                        "Retry %d/%d in %.2f seconds", 
                        str(e), retry_count, max_retries, wait_time
                    )
                    try:
                        await asyncio.sleep(wait_time)
                    except asyncio.CancelledError:
                        _LOGGER.debug("Sleep during retry backoff was cancelled, continuing with vehicle list retrieval")
                        # Continue with operation
            
            if retry_count >= max_retries:
                raise MazdaException(f"Failed to get vehicle list after {max_retries} attempts: {last_error}")

            vehicles = []
            for i, current_vec_base_info in enumerate(
                vec_base_infos_response.get("vecBaseInfos", [])
            ):
                try:
                    current_vehicle_flags = vec_base_infos_response.get("vehicleFlags", [])[i]

                    # Ignore vehicles which are not enrolled in Mazda Connected Services
                    if current_vehicle_flags.get("vinRegistStatus") != 3:
                        continue

                    # Safely parse the vehicle information JSON
                    vehicle_info = current_vec_base_info.get("Vehicle", {}).get("vehicleInformation", "{}")
                    try:
                        other_veh_info = json.loads(vehicle_info)
                    except (json.JSONDecodeError, TypeError) as e:
                        _LOGGER.warning("Error parsing vehicle info for index %d: %s", i, str(e))
                        other_veh_info = {}

                    # Get nickname with retry mechanism
                    nickname = None
                    nick_retry_count = 0
                    max_nick_retries = 2
                    try:
                        while nick_retry_count < max_nick_retries:
                            try:
                                nickname = await self.get_nickname(
                                    current_vec_base_info.get("vin")
                                )
                                break
                            except (ServerDisconnectedError, ClientConnectorError, ClientOSError) as e:
                                nick_retry_count += 1
                                if nick_retry_count >= max_nick_retries:
                                    _LOGGER.warning(
                                        "Failed to get nickname for VIN %s: %s", 
                                        current_vec_base_info.get("vin"), str(e)
                                    )
                                    nickname = ""  # Use empty string as fallback
                                else:
                                    try:
                                        await asyncio.sleep(1)  # Short delay before retry
                                    except asyncio.CancelledError:
                                        _LOGGER.debug("Sleep during nickname retry was cancelled, continuing with empty nickname")
                                        nickname = ""  # Use empty string if sleep is cancelled
                                        break
                    except MazdaException as ex:
                        _LOGGER.warning("Error retrieving nickname for vehicle %s: %s", 
                                        current_vec_base_info.get("vin", "Unknown"), str(ex))
                        nickname = ""  # Use empty string if nickname retrieval fails completely

                    # Safely access nested dictionaries with get() and provide defaults
                    other_info = other_veh_info.get("OtherInformation", {})
                    cv_service_info = other_veh_info.get("CVServiceInformation", {})
                    
                    vehicle = {
                        "vin": current_vec_base_info.get("vin"),
                        "id": current_vec_base_info.get("Vehicle", {})
                        .get("CvInformation", {})
                        .get("internalVin"),
                        "nickname": nickname,
                        "carlineCode": other_info.get("carlineCode"),
                        "carlineName": other_info.get("carlineName"),
                        "modelYear": other_info.get("modelYear"),
                        "modelCode": other_info.get("modelCode"),
                        "modelName": other_info.get("modelName"),
                        "automaticTransmission": other_info.get("transmissionType") == "A",
                        "interiorColorCode": other_info.get("interiorColorCode"),
                        "interiorColorName": other_info.get("interiorColorName"),
                        "exteriorColorCode": other_info.get("exteriorColorCode"),
                        "exteriorColorName": other_info.get("exteriorColorName"),
                        "isElectric": current_vec_base_info.get("econnectType", 0) == 1,
                        "hasFuel": cv_service_info.get("fuelType", "00") != "05"
                    }
                    
                    vehicles.append(vehicle)
                except (MazdaException, ClientError, AttributeError, KeyError, TypeError) as ex:
                    _LOGGER.warning("Error processing vehicle at index %d: %s", i, str(ex))
                    continue

            if self._use_cached_vehicle_list:
                self._cached_vehicle_list = vehicles
                
            # Record performance metrics if enabled
            if self.performance_metrics is not None and start_time is not None:
                try:
                    elapsed = time.time() - start_time
                    if hasattr(self.performance_metrics, 'record_operation'):
                        self.performance_metrics.record_operation("get_vehicles", elapsed, True)
                    elif isinstance(self.performance_metrics, dict):
                        if "get_vehicles" not in self.performance_metrics:
                            self.performance_metrics["get_vehicles"] = {"count": 0, "total_time": 0, "min_time": float('inf'), "max_time": 0}
                        
                        self.performance_metrics["get_vehicles"]["count"] += 1
                        self.performance_metrics["get_vehicles"]["total_time"] += elapsed
                        self.performance_metrics["get_vehicles"]["min_time"] = min(self.performance_metrics["get_vehicles"]["min_time"], elapsed)
                        self.performance_metrics["get_vehicles"]["max_time"] = max(self.performance_metrics["get_vehicles"]["max_time"], elapsed)
                    else:
                        _LOGGER.debug("Performance metrics enabled but object doesn't support expected interfaces")
                    
                    _LOGGER.debug("get_vehicles call completed in %.3f seconds", elapsed)
                except (AttributeError, TypeError) as e:
                    _LOGGER.warning("Error recording performance metrics: %s", str(e))
                
            # Add delay between endpoint calls if configured
            if self._endpoint_delay > 0:
                _LOGGER.debug("Sleeping for %d seconds between API endpoint calls", self._endpoint_delay)
                try:
                    await asyncio.sleep(self._endpoint_delay)
                except asyncio.CancelledError:
                    _LOGGER.debug("Sleep between API calls was cancelled, proceeding with vehicles operation")
                    # Don't re-raise, continue with the operation
                
            return vehicles
            
        except (MazdaException, ClientError) as ex:
            # Record performance metrics if enabled
            if self.performance_metrics is not None and start_time is not None:
                try:
                    elapsed = time.time() - start_time
                    if hasattr(self.performance_metrics, 'record_operation'):
                        self.performance_metrics.record_operation("get_vehicles", elapsed, False)
                    elif isinstance(self.performance_metrics, dict):
                        if "get_vehicles" not in self.performance_metrics:
                            self.performance_metrics["get_vehicles"] = {"count": 0, "total_time": 0, "min_time": float('inf'), "max_time": 0}
                        
                        self.performance_metrics["get_vehicles"]["count"] += 1
                        self.performance_metrics["get_vehicles"]["total_time"] += elapsed
                        self.performance_metrics["get_vehicles"]["min_time"] = min(self.performance_metrics["get_vehicles"]["min_time"], elapsed)
                        self.performance_metrics["get_vehicles"]["max_time"] = max(self.performance_metrics["get_vehicles"]["max_time"], elapsed)
                    else:
                        _LOGGER.debug("Performance metrics enabled but object doesn't support expected interfaces")
                    
                    _LOGGER.debug("get_vehicles call completed in %.3f seconds", elapsed)
                except (AttributeError, TypeError) as e:
                    _LOGGER.warning("Error recording performance metrics: %s", str(e))
                
            _LOGGER.error("Error getting vehicle list: %s", str(ex))
            raise

    async def get_nickname(self, vehicle_id):
        """Gets the nickname for the specified vehicle."""
        
        # Check cache first to avoid frequent API calls
        if vehicle_id in self._nickname_cache:
            # If the cache hasn't expired, return the cached value
            if self._nickname_cache_expiry.get(vehicle_id, datetime.datetime.min) > datetime.datetime.now():
                _LOGGER.debug(f"Using cached nickname for vehicle {vehicle_id}: {self._nickname_cache[vehicle_id]}")
                return self._nickname_cache[vehicle_id]
        
        start_time = time.time()
        try:
            nickname = await self.controller.get_nickname(vehicle_id, RequestPriority.HEALTH_REPORT)

            # Store in cache with expiry time
            self._nickname_cache[vehicle_id] = nickname
            self._nickname_cache_expiry[vehicle_id] = datetime.datetime.now() + self._nickname_cache_duration
            
            # Record performance metrics if enabled
            if self.performance_metrics is not None:
                try:
                    elapsed = time.time() - start_time
                    if hasattr(self.performance_metrics, 'record_operation'):
                        self.performance_metrics.record_operation("get_nickname", elapsed, True)
                    elif isinstance(self.performance_metrics, dict):
                        if "get_nickname" not in self.performance_metrics:
                            self.performance_metrics["get_nickname"] = {"count": 0, "total_time": 0, "min_time": float('inf'), "max_time": 0}
                        
                        self.performance_metrics["get_nickname"]["count"] += 1
                        self.performance_metrics["get_nickname"]["total_time"] += elapsed
                        self.performance_metrics["get_nickname"]["min_time"] = min(self.performance_metrics["get_nickname"]["min_time"], elapsed)
                        self.performance_metrics["get_nickname"]["max_time"] = max(self.performance_metrics["get_nickname"]["max_time"], elapsed)
                    else:
                        _LOGGER.debug("Performance metrics enabled but object doesn't support expected interfaces")
                    
                    _LOGGER.debug("get_nickname call completed in %.3f seconds", elapsed)
                except (AttributeError, TypeError) as e:
                    _LOGGER.warning("Error recording performance metrics: %s", str(e))
                
            return nickname
        except (MazdaException, ClientError, AttributeError, TypeError) as ex:
            # Record performance metrics if enabled
            if self.performance_metrics is not None:
                try:
                    elapsed = time.time() - start_time
                    if hasattr(self.performance_metrics, 'record_operation'):
                        self.performance_metrics.record_operation("get_nickname", elapsed, False)
                    elif isinstance(self.performance_metrics, dict):
                        if "get_nickname" not in self.performance_metrics:
                            self.performance_metrics["get_nickname"] = {"count": 0, "total_time": 0, "min_time": float('inf'), "max_time": 0}
                        
                        self.performance_metrics["get_nickname"]["count"] += 1
                        self.performance_metrics["get_nickname"]["total_time"] += elapsed
                        self.performance_metrics["get_nickname"]["min_time"] = min(self.performance_metrics["get_nickname"]["min_time"], elapsed)
                        self.performance_metrics["get_nickname"]["max_time"] = max(self.performance_metrics["get_nickname"]["max_time"], elapsed)
                    else:
                        _LOGGER.debug("Performance metrics enabled but object doesn't support expected interfaces")
                    
                    _LOGGER.debug("get_nickname call completed in %.3f seconds", elapsed)
                except (AttributeError, TypeError) as e:
                    _LOGGER.warning("Error recording performance metrics: %s", str(e))
                
            raise ex

    async def get_vehicle_status(self, vehicle_id):  # noqa: D102
        """Get the current status of a specific vehicle.
        
        Args:
            vehicle_id: The Mazda vehicle ID to get status for
            
        Returns:
            dict: The vehicle status information
        """
        start_time = time.time() if self.performance_metrics is not None else None
        
        try:
            response = await self.controller.get_vehicle_status(vehicle_id, RequestPriority.VEHICLE_STATUS)

            if response is None or "alertInfos" not in response or not response["alertInfos"]:
                _LOGGER.error(f"Invalid response received for VIN {vehicle_id}: {response}")
                return None  # Handle the case where the response is empty
            
            alert_info = response.get("alertInfos", [{}])[0]  # Use [{}] as a safe default
            remote_info = response.get("remoteInfos", [{}])[0]
            
            latitude = remote_info.get("PositionInfo", {}).get("Latitude")
            if latitude is not None:
                latitude = latitude * (
                    -1 if remote_info.get("PositionInfo", {}).get("LatitudeFlag") == 1 else 1
                )
            longitude = remote_info.get("PositionInfo", {}).get("Longitude")
            if longitude is not None:
                longitude = longitude * (
                    1 if remote_info.get("PositionInfo", {}).get("LongitudeFlag") == 1 else -1
                )
            
            vehicle_status = {
                "lastUpdatedTimestamp": alert_info.get("OccurrenceDate"),
                "latitude": latitude,
                "longitude": longitude,
                "positionTimestamp": remote_info.get("PositionInfo", {}).get(
                    "AcquisitionDatetime"
                ),
                "fuelRemainingPercent": remote_info.get("ResidualFuel", {}).get(
                    "FuelSegementDActl"
                ),
                "fuelDistanceRemainingKm": remote_info.get("ResidualFuel", {}).get(
                    "RemDrvDistDActlKm"
                ),
                "odometerKm": remote_info.get("DriveInformation", {}).get("OdoDispValue"),
                "doors": {
                    "driverDoorOpen": alert_info.get("Door", {}).get("DrStatDrv") == 1,
                    "passengerDoorOpen": alert_info.get("Door", {}).get("DrStatPsngr") == 1,
                    "rearLeftDoorOpen": alert_info.get("Door", {}).get("DrStatRl") == 1,
                    "rearRightDoorOpen": alert_info.get("Door", {}).get("DrStatRr") == 1,
                    "trunkOpen": alert_info.get("Door", {}).get("DrStatTrnkLg") == 1,
                    "hoodOpen": alert_info.get("Door", {}).get("DrStatHood") == 1,
                    "fuelLidOpen": alert_info.get("Door", {}).get("FuelLidOpenStatus") == 1,
                },
                "doorLocks": {
                    "driverDoorUnlocked": alert_info.get("Door", {}).get("LockLinkSwDrv") == 1,
                    "passengerDoorUnlocked": alert_info.get("Door", {}).get(
                        "LockLinkSwPsngr"
                    )
                    == 1,
                    "rearLeftDoorUnlocked": alert_info.get("Door", {}).get("LockLinkSwRl") == 1,
                    "rearRightDoorUnlocked": alert_info.get("Door", {}).get("LockLinkSwRr")
                    == 1,
                },
                "windows": {
                    "driverWindowOpen": alert_info.get("Pw", {}).get("PwPosDrv") == 1,
                    "passengerWindowOpen": alert_info.get("Pw", {}).get("PwPosPsngr") == 1,
                    "rearLeftWindowOpen": alert_info.get("Pw", {}).get("PwPosRl") == 1,
                    "rearRightWindowOpen": alert_info.get("Pw", {}).get("PwPosRr") == 1,
                },
                "hazardLightsOn": alert_info.get("HazardLamp", {}).get("HazardSw") == 1,
                "tirePressure": {
                    "frontLeftTirePressurePsi": remote_info.get("TPMSInformation", {}).get(
                        "FLTPrsDispPsi"
                    ),
                    "frontRightTirePressurePsi": remote_info.get("TPMSInformation", {}).get(
                        "FRTPrsDispPsi"
                    ),
                    "rearLeftTirePressurePsi": remote_info.get("TPMSInformation", {}).get(
                        "RLTPrsDispPsi"
                    ),
                    "rearRightTirePressurePsi": remote_info.get("TPMSInformation", {}).get(
                        "RRTPrsDispPsi"
                    ),
                },
            }
            
            door_lock_status = vehicle_status["doorLocks"]
            lock_value = not (
                door_lock_status["driverDoorUnlocked"]
                or door_lock_status["passengerDoorUnlocked"]
                or door_lock_status["rearLeftDoorUnlocked"]
                or door_lock_status["rearRightDoorUnlocked"]
            )
            
            self.__save_api_value(
                vehicle_id,
                "lock_state",
                lock_value,
                datetime.datetime.strptime(
                    vehicle_status["lastUpdatedTimestamp"], "%Y%m%d%H%M%S"
                ).replace(tzinfo=datetime.UTC),
            )
            
            # Track performance metrics if enabled
            if start_time is not None and self.performance_metrics is not None:
                try:
                    elapsed = time.time() - start_time
                    if hasattr(self.performance_metrics, 'record_operation'):
                        # Use record_operation method if it exists
                        self.performance_metrics.record_operation("get_vehicle_status", elapsed, True)
                    elif isinstance(self.performance_metrics, dict):
                        # Fall back to dict-based metrics tracking
                        if "get_vehicle_status" not in self.performance_metrics:
                            self.performance_metrics["get_vehicle_status"] = {"count": 0, "total_time": 0, "min_time": float('inf'), "max_time": 0}
                        
                        self.performance_metrics["get_vehicle_status"]["count"] += 1
                        self.performance_metrics["get_vehicle_status"]["total_time"] += elapsed
                        self.performance_metrics["get_vehicle_status"]["min_time"] = min(self.performance_metrics["get_vehicle_status"]["min_time"], elapsed)
                        self.performance_metrics["get_vehicle_status"]["max_time"] = max(self.performance_metrics["get_vehicle_status"]["max_time"], elapsed)
                    else:
                        _LOGGER.debug("Performance metrics enabled but object doesn't support expected interfaces")
                    
                    _LOGGER.debug("get_vehicle_status call completed in %.3f seconds", elapsed)
                except (AttributeError, TypeError) as e:
                    _LOGGER.warning("Error recording performance metrics: %s", str(e))
                
            # Add delay between endpoint calls if configured
            if self._endpoint_delay > 0:
                _LOGGER.debug("Sleeping for %d seconds between API endpoint calls", self._endpoint_delay)
                try:
                    await asyncio.sleep(self._endpoint_delay)
                except asyncio.CancelledError:
                    _LOGGER.debug("Sleep between API calls was cancelled, proceeding with vehicle status request")
                    # Don't re-raise, continue with the operation
                
            return vehicle_status
            
        except (MazdaException, ClientError) as ex:
            _LOGGER.error("Error getting vehicle status for %s: %s", vehicle_id, str(ex))
            raise

    async def get_health_reports(self, vehicle_id):  # noqa: D102
        """Get health reports for a specific vehicle.
        
        Args:
            vehicle_id: The Mazda vehicle ID to get health reports for
            
        Returns:
            list: A list of health report information
        """
        start_time = time.time() if self.performance_metrics is not None else None
        
        try:
            response = await self.controller.get_health_reports(vehicle_id, RequestPriority.HEALTH_REPORT)
            
            # Track performance metrics if enabled
            if start_time is not None and self.performance_metrics is not None:
                try:
                    elapsed = time.time() - start_time
                    if hasattr(self.performance_metrics, 'record_operation'):
                        # Use record_operation method if it exists
                        self.performance_metrics.record_operation("get_health_reports", elapsed, True)
                    elif isinstance(self.performance_metrics, dict):
                        # Fall back to dict-based metrics tracking
                        if "get_health_reports" not in self.performance_metrics:
                            self.performance_metrics["get_health_reports"] = {"count": 0, "total_time": 0, "min_time": float('inf'), "max_time": 0}
                        
                        self.performance_metrics["get_health_reports"]["count"] += 1
                        self.performance_metrics["get_health_reports"]["total_time"] += elapsed
                        self.performance_metrics["get_health_reports"]["min_time"] = min(self.performance_metrics["get_health_reports"]["min_time"], elapsed)
                        self.performance_metrics["get_health_reports"]["max_time"] = max(self.performance_metrics["get_health_reports"]["max_time"], elapsed)
                    else:
                        _LOGGER.debug("Performance metrics enabled but object doesn't support expected interfaces")
                    
                    _LOGGER.debug("get_health_reports call completed in %.3f seconds", elapsed)
                except (AttributeError, TypeError) as e:
                    _LOGGER.warning("Error recording performance metrics: %s", str(e))
                
            # Add delay between endpoint calls if configured
            if self._endpoint_delay > 0:
                _LOGGER.debug("Sleeping for %d seconds between API endpoint calls", self._endpoint_delay)
                try:
                    await asyncio.sleep(self._endpoint_delay)
                except asyncio.CancelledError:
                    _LOGGER.debug("Sleep between API calls was cancelled, proceeding with health report operation")
                    # Don't re-raise, continue with the operation
                
            return response
            
        except (MazdaException, ClientError) as ex:
            _LOGGER.error("Error getting health reports for %s: %s", vehicle_id, str(ex))
            raise

    async def get_ev_vehicle_status(self, vehicle_id):  # noqa: D102
        ev_vehicle_status_response = await self.controller.get_ev_vehicle_status(
            vehicle_id, RequestPriority.VEHICLE_STATUS
        )

        result_data = ev_vehicle_status_response.get("resultData")[0]
        vehicle_info = result_data.get("PlusBInformation", {}).get("VehicleInfo", {})
        charge_info = vehicle_info.get("ChargeInfo", {})
        hvac_info = vehicle_info.get("RemoteHvacInfo", {})

        ev_vehicle_status = {
            "lastUpdatedTimestamp": result_data.get("OccurrenceDate"),
            "chargeInfo": {
                "batteryLevelPercentage": charge_info.get("SmaphSOC"),
                "drivingRangeKm": charge_info.get("SmaphRemDrvDistKm"),
                "drivingRangeBevKm": charge_info.get("BatRemDrvDistKm"),
                "pluggedIn": charge_info.get("ChargerConnectorFitting") == 1,
                "charging": charge_info.get("ChargeStatusSub") == 6,
                "basicChargeTimeMinutes": charge_info.get("MaxChargeMinuteAC"),
                "quickChargeTimeMinutes": charge_info.get("MaxChargeMinuteQBC"),
                "batteryHeaterAuto": charge_info.get("CstmzStatBatHeatAutoSW") == 1,
                "batteryHeaterOn": charge_info.get("BatteryHeaterON") == 1,
            },
            "hvacInfo": {
                "hvacOn": hvac_info.get("HVAC") == 1,
                "frontDefroster": hvac_info.get("FrontDefroster") == 1,
                "rearDefroster": hvac_info.get("RearDefogger") == 1,
                "interiorTemperatureCelsius": hvac_info.get("InCarTeDC"),
            },
        }

        self.__save_api_value(
            vehicle_id,
            "hvac_mode",
            ev_vehicle_status["hvacInfo"]["hvacOn"],
            datetime.datetime.strptime(
                ev_vehicle_status["lastUpdatedTimestamp"], "%Y%m%d%H%M%S"
            ).replace(tzinfo=datetime.UTC),
        )

        return ev_vehicle_status

    async def get_health_report(self, vehicle_id):  # noqa: D102
        """Get the health report for a vehicle.
        
        This may include different sensors for different vehicle models.
        """
        try:
            report = await self.controller.get_health_report(vehicle_id, RequestPriority.HEALTH_REPORT)
            return report
        except (MazdaException, ClientError) as ex:
            _LOGGER.error("Error retrieving health report for vehicle %s: %s", vehicle_id, ex)
            return None

    def get_assumed_lock_state(self, vehicle_id):  # noqa: D102
        return self.__get_assumed_value(
            vehicle_id, "lock_state", datetime.timedelta(seconds=600)
        )

    def get_assumed_hvac_mode(self, vehicle_id):  # noqa: D102
        return self.__get_assumed_value(
            vehicle_id, "hvac_mode", datetime.timedelta(seconds=600)
        )

    def get_assumed_hvac_setting(self, vehicle_id):  # noqa: D102
        return self.__get_assumed_value(
            vehicle_id, "hvac_setting", datetime.timedelta(seconds=600)
        )

    async def turn_on_hazard_lights(self, vehicle_id):  # noqa: D102
        await self.controller.light_on(vehicle_id, RequestPriority.USER_COMMAND)

    async def turn_off_hazard_lights(self, vehicle_id):  # noqa: D102
        await self.controller.light_off(vehicle_id, RequestPriority.USER_COMMAND)

    async def unlock_doors(self, vehicle_id):  # noqa: D102
        self.__save_assumed_value(vehicle_id, "lock_state", False)

        await self.controller.door_unlock(vehicle_id, RequestPriority.USER_COMMAND)

    async def lock_doors(self, vehicle_id):  # noqa: D102
        self.__save_assumed_value(vehicle_id, "lock_state", True)

        await self.controller.door_lock(vehicle_id, RequestPriority.USER_COMMAND)

    async def start_engine(self, vehicle_id):  # noqa: D102
        await self.controller.engine_start(vehicle_id, RequestPriority.USER_COMMAND)

    async def stop_engine(self, vehicle_id):  # noqa: D102
        await self.controller.engine_stop(vehicle_id, RequestPriority.USER_COMMAND)

    async def send_poi(self, vehicle_id, latitude, longitude, name):  # noqa: D102
        await self.controller.send_poi(vehicle_id, latitude, longitude, name, RequestPriority.HEALTH_REPORT)

    async def start_charging(self, vehicle_id):  # noqa: D102
        await self.controller.charge_start(vehicle_id, RequestPriority.USER_COMMAND)

    async def stop_charging(self, vehicle_id):  # noqa: D102
        await self.controller.charge_stop(vehicle_id, RequestPriority.USER_COMMAND)

    async def get_hvac_setting(self, vehicle_id):  # noqa: D102
        response = await self.controller.get_hvac_setting(vehicle_id, RequestPriority.HEALTH_REPORT)

        response_hvac_settings = response.get("hvacSettings", {})

        hvac_setting = {
            "temperature": response_hvac_settings.get("Temperature"),
            "temperatureUnit": "C"
            if response_hvac_settings.get("TemperatureType") == 1
            else "F",
            "frontDefroster": response_hvac_settings.get("FrontDefroster") == 1,
            "rearDefroster": response_hvac_settings.get("RearDefogger") == 1,
        }

        self.__save_api_value(vehicle_id, "hvac_setting", hvac_setting)

        return hvac_setting

    async def set_hvac_setting(  # noqa: D102
        self, vehicle_id, temperature, temperature_unit, front_defroster, rear_defroster
    ):
        self.__save_assumed_value(
            vehicle_id,
            "hvac_setting",
            {
                "temperature": temperature,
                "temperatureUnit": temperature_unit,
                "frontDefroster": front_defroster,
                "rearDefroster": rear_defroster,
            },
        )

        await self.controller.set_hvac_setting(
            vehicle_id, temperature, temperature_unit, front_defroster, rear_defroster, RequestPriority.USER_COMMAND
        )

    async def turn_on_hvac(self, vehicle_id):  # noqa: D102
        self.__save_assumed_value(vehicle_id, "hvac_mode", True)

        await self.controller.hvac_on(vehicle_id, RequestPriority.USER_COMMAND)

    async def turn_off_hvac(self, vehicle_id):  # noqa: D102
        self.__save_assumed_value(vehicle_id, "hvac_mode", False)

        await self.controller.hvac_off(vehicle_id, RequestPriority.USER_COMMAND)

    async def refresh_vehicle_status(self, vehicle_id):  # noqa: D102
        await self.controller.refresh_vehicle_status(vehicle_id, RequestPriority.USER_COMMAND)

    async def update_vehicle_nickname(self, vin, new_nickname):  # noqa: D102
        await self.controller.update_nickname(vin, new_nickname, RequestPriority.HEALTH_REPORT)

    async def close(self):  # noqa: D102
        await self.controller.close()

    def __get_assumed_value(self, vehicle_id, key, assumed_state_validity_duration):
        cached_state = self.__get_cached_state(vehicle_id)

        assumed_value_key = "assumed_" + key
        api_value_key = "api_" + key
        assumed_value_timestamp_key = assumed_value_key + "_timestamp"
        api_value_timestamp_key = api_value_key + "_timestamp"

        if assumed_value_key not in cached_state and api_value_key not in cached_state:
            return None

        if assumed_value_key in cached_state and api_value_key not in cached_state:
            return cached_state.get(assumed_value_key)

        if assumed_value_key not in cached_state and api_value_key in cached_state:
            return cached_state.get(api_value_key)

        now_timestamp = datetime.datetime.now(datetime.UTC)

        if (
            assumed_value_timestamp_key in cached_state
            and api_value_timestamp_key in cached_state
            and cached_state.get(assumed_value_timestamp_key)
            > cached_state.get(api_value_timestamp_key)
            and (now_timestamp - cached_state.get(assumed_value_timestamp_key))
            < assumed_state_validity_duration
        ):
            return cached_state.get(assumed_value_key)

        return cached_state.get(api_value_key)

    def __save_assumed_value(self, vehicle_id, key, value, timestamp=None):
        cached_state = self.__get_cached_state(vehicle_id)

        timestamp_value = (
            timestamp if timestamp is not None else datetime.datetime.now(datetime.UTC)
        )

        cached_state["assumed_" + key] = value
        cached_state["assumed_" + key + "_timestamp"] = timestamp_value

    def __save_api_value(self, vehicle_id, key, value, timestamp=None):
        cached_state = self.__get_cached_state(vehicle_id)

        timestamp_value = (
            timestamp if timestamp is not None else datetime.datetime.now(datetime.UTC)
        )

        cached_state["api_" + key] = value
        cached_state["api_" + key + "_timestamp"] = timestamp_value

    def __get_cached_state(self, vehicle_id):
        if vehicle_id not in self._cached_state:
            self._cached_state[vehicle_id] = {}

        return self._cached_state[vehicle_id]
