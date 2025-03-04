import hashlib  # noqa: D100

from .connection import Connection
from .exceptions import MazdaException
from ..priority_lock import RequestPriority
import logging

_LOGGER = logging.getLogger(__name__)

class Controller:  # noqa: D101
    def __init__(self, email, password, region, websession=None, log_api_responses=False):  # noqa: D107
        self.connection = Connection(email, password, region, websession)
        self.log_api_responses = log_api_responses

    async def login(self, priority=RequestPriority.HEALTH_REPORT):  # noqa: D102
        await self.connection.login(priority=priority)

    async def get_tac(self, priority=RequestPriority.HEALTH_REPORT):  # noqa: D102
        return await self.connection.api_request(
            "GET", "content/getTac/v4", needs_keys=True, needs_auth=False, priority=priority
        )

    async def get_language_pkg(self, priority=RequestPriority.HEALTH_REPORT):  # noqa: D102
        postBody = {"platformType": "ANDROID", "region": "MNAO", "version": "2.0.4"}
        return await self.connection.api_request(
            "POST",
            "junction/getLanguagePkg/v4",
            body_dict=postBody,
            needs_keys=True,
            needs_auth=False,
            priority=priority,
        )

    async def get_vec_base_infos(self, priority=RequestPriority.VEHICLE_STATUS):  # noqa: D102
        return await self.connection.api_request(
            "POST",
            "remoteServices/getVecBaseInfos/v4",
            body_dict={"internaluserid": "__INTERNAL_ID__"},
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

    async def get_vehicle_status(self, internal_vin, priority=RequestPriority.VEHICLE_STATUS):  # noqa: D102
        post_body = {
            "internaluserid": "__INTERNAL_ID__",
            "internalvin": internal_vin,
            "limit": 1,
            "offset": 0,
            "vecinfotype": "0",
        }
        response = await self.connection.api_request(
            "POST",
            "remoteServices/getVehicleStatus/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to get vehicle status")

        return response

    async def get_ev_vehicle_status(self, internal_vin, priority=RequestPriority.VEHICLE_STATUS):  # noqa: D102
        post_body = {
            "internaluserid": "__INTERNAL_ID__",
            "internalvin": internal_vin,
            "limit": 1,
            "offset": 0,
            "vecinfotype": "0",
        }
        response = await self.connection.api_request(
            "POST",
            "remoteServices/getEVVehicleStatus/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to get EV vehicle status")

        return response

    async def get_health_report(self, internal_vin, priority=RequestPriority.HEALTH_REPORT):  # noqa: D102
        post_body = {
            "internaluserid": "__INTERNAL_ID__",
            "internalvin": internal_vin,
            "limit": 1,
            "offset": 0,
        }

        _LOGGER.debug(f"Sending health report request for vehicle ID: {internal_vin}")
        
        response = await self.connection.api_request(
            "POST",
            "remoteServices/getHealthReport/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            _LOGGER.error(f"Failed to get health report for vehicle ID {internal_vin}: {response.get('resultCode', 'Unknown error')}")
            raise MazdaException(f"Failed to get health report: {response.get('resultCode', 'Unknown error')}")

        _LOGGER.debug(f"Health report API call succeeded for vehicle ID {internal_vin} with result code: {response['resultCode']}")
        
        # Check for different health report data structures
        if "healthReportData" in response:
            # Original structure with healthReportData
            vhcle_data = response.get("healthReportData", {}).get("vhcle", {})
            report_date = vhcle_data.get("reportDate", "Unknown")
            report_items_count = len(vhcle_data.get("reportItems", []))
            _LOGGER.info(f"Health report retrieved for vehicle {internal_vin}: date={report_date}, items={report_items_count}")
        elif "remoteInfos" in response and isinstance(response["remoteInfos"], list) and len(response["remoteInfos"]) > 0:
            # New structure with remoteInfos array
            remote_info = response["remoteInfos"][0]
            occurrence_date = remote_info.get("OccurrenceDate", "Unknown")
            _LOGGER.info(f"Health report retrieved for vehicle {internal_vin} with occurrence date: {occurrence_date}")
        else:
            _LOGGER.warning(f"Health report for vehicle {internal_vin} has unexpected structure (missing both healthReportData and remoteInfos)")

        return response

    async def door_unlock(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/doorUnlock/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to unlock door")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Door unlock command sent with visitNo: {response['visitNo']}")
        
        return response

    async def door_lock(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/doorLock/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to lock door")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Door lock command sent with visitNo: {response['visitNo']}")
        
        return response

    async def get_command_status(self, internal_vin, visit_no, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        """Get the status of a remote command using the visitNo.
        
        Args:
            internal_vin: Internal VIN of the vehicle
            visit_no: The visitNo from the original command response
            
        Returns:
            dict: Command status information
        """
        post_body = {
            "internaluserid": "__INTERNAL_ID__",
            "internalvin": internal_vin,
            "visitNo": visit_no
        }

        response = await self.connection.api_request(
            "POST",
            "remoteServices/getVehicleCommandStatus/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if self.log_api_responses:
            _LOGGER.debug(f"Command status response: {response}")

        return response

    async def light_on(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/lightOn/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to turn light on")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Light on command sent with visitNo: {response['visitNo']}")
        
        return response

    async def light_off(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/lightOff/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to turn light off")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Light off command sent with visitNo: {response['visitNo']}")
        
        return response

    async def engine_start(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/engineStart/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to start engine")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Engine start command sent with visitNo: {response['visitNo']}")
        
        return response

    async def engine_stop(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/engineStop/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to stop engine")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Engine stop command sent with visitNo: {response['visitNo']}")
        
        return response

    async def get_nickname(self, vin, priority=RequestPriority.HEALTH_REPORT):  # noqa: D102
        if len(vin) != 17:
            raise MazdaException("Invalid VIN")

        post_body = {"internaluserid": "__INTERNAL_ID__", "vin": vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/getNickName/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to get vehicle nickname")

        # Ensure we log the response to debug potential issues
        nickname = response.get("nickname") or response.get("vtitle") or response["carlineDesc"]
        _LOGGER.debug(f"Retrieved nickname for VIN {vin}: {nickname}")

        return nickname  # This now prioritizes nickname > vtitle > carlineDesc


    async def update_nickname(self, vin, new_nickname, priority=RequestPriority.HEALTH_REPORT):  # noqa: D102
        if len(vin) != 17:
            raise MazdaException("Invalid VIN")
        if len(new_nickname) > 20:
            raise MazdaException("Nickname is too long")

        post_body = {
            "internaluserid": "__INTERNAL_ID__",
            "vin": vin,
            "vtitle": new_nickname,
        }

        response = await self.connection.api_request(
            "POST",
            "remoteServices/updateNickName/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to update vehicle nickname")

        _LOGGER.debug(f"Successfully updated nickname for VIN {vin} to {new_nickname}")

    async def send_poi(self, internal_vin, latitude, longitude, name, priority=RequestPriority.HEALTH_REPORT):  # noqa: D102
        # Calculate a POI ID that is unique to the name and location
        poi_id = hashlib.sha256(
            (str(name) + str(latitude) + str(longitude)).encode()
        ).hexdigest()[0:10]

        post_body = {
            "internaluserid": "__INTERNAL_ID__",
            "internalvin": internal_vin,
            "placemarkinfos": [
                {
                    "Altitude": 0,
                    "Latitude": abs(latitude),
                    "LatitudeFlag": 0 if (latitude >= 0) else 1,
                    "Longitude": abs(longitude),
                    "LongitudeFlag": 0 if (longitude < 0) else 1,
                    "Name": name,
                    "OtherInformation": "{}",
                    "PoiId": poi_id,
                    "source": "google",
                }
            ],
        }

        response = await self.connection.api_request(
            "POST",
            "remoteServices/sendPOI/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to send POI")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Send POI command sent with visitNo: {response['visitNo']}")
        
        return response

    async def charge_start(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/chargeStart/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to start charging")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Charge start command sent with visitNo: {response['visitNo']}")
        
        return response

    async def charge_stop(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/chargeStop/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to stop charging")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Charge stop command sent with visitNo: {response['visitNo']}")
        
        return response

    async def get_hvac_setting(self, internal_vin, priority=RequestPriority.VEHICLE_STATUS):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/getHVACSetting/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to get HVAC setting")

        return response

    async def set_hvac_setting(  # noqa: D102
        self,
        internal_vin,
        temperature,
        temperature_unit,
        front_defroster,
        rear_defroster,
        priority=RequestPriority.USER_COMMAND,
    ):
        post_body = {
            "internaluserid": "__INTERNAL_ID__",
            "internalvin": internal_vin,
            "hvacsettings": {
                "FrontDefroster": 1 if front_defroster else 0,
                "RearDefogger": 1 if rear_defroster else 0,
                "Temperature": temperature,
                "TemperatureType": 1 if temperature_unit.lower() == "c" else 2,
            },
        }

        response = await self.connection.api_request(
            "POST",
            "remoteServices/updateHVACSetting/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to set HVAC setting")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"Set HVAC setting command sent with visitNo: {response['visitNo']}")
        
        return response

    async def hvac_on(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/hvacOn/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to turn HVAC on")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"HVAC on command sent with visitNo: {response['visitNo']}")
        
        return response

    async def hvac_off(self, internal_vin, priority=RequestPriority.USER_COMMAND):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/hvacOff/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to turn HVAC off")

        # Return the command response with the visitNo which can be used to track status
        if "visitNo" in response:
            _LOGGER.debug(f"HVAC off command sent with visitNo: {response['visitNo']}")
        
        return response

    async def refresh_vehicle_status(self, internal_vin, priority=RequestPriority.VEHICLE_STATUS):  # noqa: D102
        post_body = {"internaluserid": "__INTERNAL_ID__", "internalvin": internal_vin}

        response = await self.connection.api_request(
            "POST",
            "remoteServices/activeRealTimeVehicleStatus/v4",
            body_dict=post_body,
            needs_keys=True,
            needs_auth=True,
            priority=priority,
        )

        if response["resultCode"] != "200S00":
            raise MazdaException("Failed to refresh vehicle status")

        return response

    async def close(self):  # noqa: D102
        await self.connection.close()
