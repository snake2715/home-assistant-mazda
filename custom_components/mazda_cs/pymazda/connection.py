import asyncio  # noqa: D100
import base64
import hashlib
import json
import logging
import ssl
import time
from urllib.parse import urlencode

import aiohttp
from aiohttp.client_exceptions import ServerDisconnectedError, ClientConnectorError, ClientOSError, ClientResponseError
from aiohttp import ClientTimeout, ClientError

from .crypto_utils import (
    decrypt_aes128cbc_buffer_to_str,
    encrypt_aes128cbc_buffer_to_base64_str,
    encrypt_rsaecbpkcs1_padding,
    generate_usher_device_id_from_seed,
    generate_uuid_from_seed,
)
from .exceptions import (
    MazdaAccountLockedException,
    MazdaAPIEncryptionException,
    MazdaAuthenticationException,
    MazdaConfigException,
    MazdaException,
    MazdaLoginFailedException,
    MazdaRequestInProgressException,
    MazdaTokenExpiredException,
)
from .sensordata.sensor_data_builder import SensorDataBuilder
from .ssl_context_configurator.ssl_context_configurator import SSLContextConfigurator
from ..priority_lock import get_account_lock, RequestPriority

ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.load_default_certs()
ssl_context.set_ciphers("TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA:AES256-SHA")

SSL_SIGNATURE_ALGORITHMS = [
    "ecdsa_secp256r1_sha256",
    "rsa_pss_rsae_sha256",
    "rsa_pkcs1_sha256",
    "ecdsa_secp384r1_sha384",
    "rsa_pss_rsae_sha384",
    "rsa_pkcs1_sha384",
    "rsa_pss_rsae_sha512",
    "rsa_pkcs1_sha512",
    "rsa_pkcs1_sha1",
]
with SSLContextConfigurator(ssl_context, libssl_path="libssl.so.3") as ssl_context_configurator:
    ssl_context_configurator.configure_signature_algorithms(":".join(SSL_SIGNATURE_ALGORITHMS))


REGION_CONFIG = {
    "MNAO": {
        "app_code": "202007270941270111799",
        "base_url": "https://0cxo7m58.mazda.com/prod/",
        "usher_url": "https://ptznwbh8.mazda.com/appapi/v1/",
    },
    "MME": {
        "app_code": "202008100250281064816",
        "base_url": "https://e9stj7g7.mazda.com/prod/",
        "usher_url": "https://rz97suam.mazda.com/appapi/v1/",
    },
    "MJO": {
        "app_code": "202009170613074283422",
        "base_url": "https://wcs9p6wj.mazda.com/prod/",
        "usher_url": "https://c5ulfwxr.mazda.com/appapi/v1/",
    },
}

IV = "0102030405060708"
SIGNATURE_MD5 = "C383D8C4D279B78130AD52DC71D95CAA"
APP_PACKAGE_ID = "com.interrait.mymazda"
USER_AGENT_BASE_API = "MyMazda-Android/8.5.2"
USER_AGENT_USHER_API = "MyMazda/8.5.2 (Google Pixel 3a; Android 11)"
APP_OS = "Android"
APP_VERSION = "8.5.2"
USHER_SDK_VERSION = "11.3.0700.001"

MAX_RETRIES = 8  # Increased from 4 to allow more retries

class Connection:
    """Main class for handling MyMazda API connection."""

    def __init__(self, email, password, region, websession=None):  # noqa: D107
        self.email = email
        self.password = password

        if region in REGION_CONFIG:
            region_config = REGION_CONFIG[region]
            self.app_code = region_config["app_code"]
            self.base_url = region_config["base_url"]
            self.usher_url = region_config["usher_url"]
        else:
            raise MazdaConfigException("Invalid region")

        self.base_api_device_id = generate_uuid_from_seed(email)
        self.usher_api_device_id = generate_usher_device_id_from_seed(email)

        self.enc_key = None
        self.sign_key = None

        self.access_token = None
        self.access_token_expiration_ts = None

        self.sensor_data_builder = SensorDataBuilder()

        if websession is None:
            self._create_session()
        else:
            self._session = websession

        self.logger = logging.getLogger(__name__)

        self.account_lock = get_account_lock(email)

    def _create_session(self):
        """Create a new aiohttp session with appropriate headers"""
        if hasattr(self, '_session') and not self._session.closed:
            # Close existing session if there is one
            try:
                self._session.close()
            except (AttributeError, OSError) as e:
                self.logger.debug(f"Error closing previous session: {e}")
                pass
                
        # Create new session with default headers
        self._session = aiohttp.ClientSession(
            headers={
                "device-id": self.base_api_device_id,
                "app-code": self.app_code,
                "user-agent": USER_AGENT_BASE_API,
                "app-version": APP_VERSION,
                "app-unique-id": APP_PACKAGE_ID,
            }
        )
        self.logger.debug("Created new aiohttp session")

    async def _recover_session(self):
        """Recover from connection issues by recreating the session and logging in again"""
        self.logger.info("Recovering session due to persistent connection issues")
        # Create a new session
        self._create_session()
        # Reset login state
        self.access_token = None
        self.access_token_expiration_ts = None
        # Try to log in again
        try:
            await self.login(priority=RequestPriority.USER_COMMAND)
            self.logger.info("Session recovery complete")
        except Exception as e:
            self.logger.error("Session recovery failed: %s", str(e))
            raise

    def __get_timestamp_str_ms(self):
        return str(int(round(time.time() * 1000)))

    def __get_timestamp_str(self):
        return str(int(round(time.time())))

    def __get_decryption_key_from_app_code(self):
        val1 = (
            hashlib.md5((self.app_code + APP_PACKAGE_ID).encode()).hexdigest().upper()
        )
        val2 = hashlib.md5((val1 + SIGNATURE_MD5).encode()).hexdigest().lower()
        return val2[4:20]

    def __get_temporary_sign_key_from_app_code(self):
        val1 = (
            hashlib.md5((self.app_code + APP_PACKAGE_ID).encode()).hexdigest().upper()
        )
        val2 = hashlib.md5((val1 + SIGNATURE_MD5).encode()).hexdigest().lower()
        return val2[20:32] + val2[0:10] + val2[4:6]

    def __get_sign_from_timestamp(self, timestamp):
        if timestamp is None or timestamp == "":
            return ""

        timestamp_extended = (timestamp + timestamp[6:] + timestamp[3:]).upper()

        temporary_sign_key = self.__get_temporary_sign_key_from_app_code()

        return self.__get_payload_sign(timestamp_extended, temporary_sign_key).upper()

    def __get_sign_from_payload_and_timestamp(self, payload, timestamp):
        if timestamp is None or timestamp == "":
            return ""
        if self.sign_key is None or self.sign_key == "":
            raise MazdaException("Missing sign key")

        return self.__get_payload_sign(
            self.__encrypt_payload_using_key(payload)
            + timestamp
            + timestamp[6:]
            + timestamp[3:],
            self.sign_key,
        )

    def __get_payload_sign(self, encrypted_payload_and_timestamp, sign_key):
        return (
            hashlib.sha256((encrypted_payload_and_timestamp + sign_key).encode())
            .hexdigest()
            .upper()
        )

    def __encrypt_payload_using_key(self, payload):
        if self.enc_key is None or self.enc_key == "":
            raise MazdaException("Missing encryption key")
        if payload is None or payload == "":
            return ""

        return encrypt_aes128cbc_buffer_to_base64_str(
            payload.encode("utf-8"), self.enc_key, IV
        )

    def __decrypt_payload_using_app_code(self, payload):
        buf = base64.b64decode(payload)
        key = self.__get_decryption_key_from_app_code()
        decrypted = decrypt_aes128cbc_buffer_to_str(buf, key, IV)
        return json.loads(decrypted)

    def __decrypt_payload_using_key(self, payload):
        if self.enc_key is None or self.enc_key == "":
            raise MazdaException("Missing encryption key")

        buf = base64.b64decode(payload)
        decrypted = decrypt_aes128cbc_buffer_to_str(buf, self.enc_key, IV)
        return json.loads(decrypted)

    def __encrypt_payload_with_public_key(self, password, public_key):
        timestamp = self.__get_timestamp_str()
        encryptedBuffer = encrypt_rsaecbpkcs1_padding(
            password + ":" + timestamp, public_key
        )
        return base64.b64encode(encryptedBuffer).decode("utf-8")

    async def api_request(  # noqa: D102
        self,
        method,
        uri,
        query_dict={},
        body_dict={},
        needs_keys=True,
        needs_auth=False,
        priority=RequestPriority.VEHICLE_STATUS,
    ):
        return await self.__api_request_retry(
            method, uri, query_dict, body_dict, needs_keys, needs_auth, num_retries=0, priority=priority
        )

    async def __api_request_retry(
        self,
        method,
        uri,
        query_dict={},
        body_dict={},
        needs_keys=True,
        needs_auth=False,
        num_retries=0,
        priority=RequestPriority.VEHICLE_STATUS,
    ):
        if num_retries > MAX_RETRIES:
            self.logger.error("Request to %s exceeded max retries (%d). Giving up.", uri, MAX_RETRIES)
            if "getNickName" in uri:
                # Return empty response for non-critical endpoints
                self.logger.warning("Non-critical endpoint failed (getNickName), returning empty result")
                return {"resultCode": "999", "carlineDesc": "", "visitNo": ""}
            raise MazdaException(f"Request exceeded max number of retries ({MAX_RETRIES})")

        if needs_keys:
            await self.__ensure_keys_present()
        if needs_auth:
            await self.__ensure_token_is_valid()

        retry_message = (
            (" - attempt #" + str(num_retries + 1)) if (num_retries > 0) else ""
        )
        if "getHealthReport" in uri:
            self.logger.debug(
                f"Sending {method} request to {uri}{retry_message} for health report discovery"  # noqa: G004
            )
        else:
            self.logger.debug(
                f"Sending {method} request to {uri}{retry_message}"  # noqa: G004
            )

        # Get operation name for lock tracking
        operation_name = uri
        if "getHealthReport" in uri:
            operation_name = "health_report"
        elif "getVecBaseInfos" in uri:
            operation_name = "vehicle_status"
        elif "getNickName" in uri:
            operation_name = "nickname"
        elif "doorUnlock" in uri or "doorLock" in uri or "engineStart" in uri or "engineStop" in uri:
            operation_name = "user_command"

        # Acquire the priority lock before making the request
        lock_acquired = False
        try:
            await self.account_lock.acquire(priority, operation_name)
            lock_acquired = True
            
            response = await self.__send_api_request(
                method, uri, query_dict, body_dict, needs_keys, needs_auth
            )
            
            # Success! Release the lock before returning
            if lock_acquired:
                self.account_lock.release()
                lock_acquired = False
                
            return response
            
        except (ClientError, OSError, asyncio.TimeoutError) as e:
            error_details = str(e) if str(e) else type(e).__name__
            retry_after = min(5 * (num_retries + 1), 30)  # Progressive backoff, max 30 seconds
            
            # Log connection errors with better error details
            if "getVecBaseInfos" in uri and num_retries > 5:
                # For vehicle info requests, log special message after many attempts
                self.logger.error(
                    f"Persistent connection issues with Mazda servers when requesting vehicle information. "
                    f"This may indicate temporary API unavailability. Error: {error_details}"
                )
            else:
                self.logger.warning(
                    f"Server connection error: {error_details}. Waiting {retry_after} seconds before retry."
                )
                
            # For server disconnections, log the error
            if "disconnected" in str(e).lower():
                self.logger.error(f"Connection error during API request to {uri}: Server disconnected")
                
            # If we've already tried many times, add more delay to prevent excessive retries
            if num_retries >= 5:
                retry_after = min(retry_after + 10, 60)  # Add extra delay after many retries, cap at 60s
                
            # Release the priority lock before waiting
            if lock_acquired:
                self.account_lock.release()
                lock_acquired = False
            
            await asyncio.sleep(retry_after)
            
            # Limit maximum retries to prevent infinite loops
            max_retries = 12  # Approximately 5-10 minutes of retrying with progressive backoff
            if num_retries >= max_retries:
                self.logger.error(f"Maximum retries ({max_retries}) exceeded for {uri}. Giving up.")
                raise MazdaException(f"Failed to connect to Mazda servers after {max_retries} attempts")
                
            # Recover session if we've tried many times
            if num_retries >= 6:
                await self._recover_session()
                
            # Recursive call WITHOUT the lock still acquired
            return await self.__api_request_retry(
                method,
                uri,
                query_dict,
                body_dict,
                needs_keys,
                needs_auth,
                num_retries + 1,
                priority=priority,
            )
        except (ClientResponseError, MazdaAPIEncryptionException, MazdaTokenExpiredException, 
                MazdaLoginFailedException, MazdaRequestInProgressException) as e:
            # Release the priority lock before handling the exception
            if lock_acquired:
                self.account_lock.release()
                lock_acquired = False
            
            if isinstance(e, ClientResponseError):
                self.logger.error(f"Request to {uri} failed with status {e.status}: {e.message}")
                raise  # Re-raise for the retry mechanism to handle
            elif isinstance(e, MazdaAPIEncryptionException):
                self.logger.info(
                    "Server reports request was not encrypted properly. Retrieving new encryption keys."
                )
                await self.__retrieve_keys()
            elif isinstance(e, MazdaTokenExpiredException):
                self.logger.info(
                    "Server reports access token was expired. Fetching a new one."
                )
                await self.login(priority=priority)
            elif isinstance(e, MazdaLoginFailedException):
                self.logger.warning("Login failed for an unknown reason. Trying again.")
                await self.login(priority=priority)
            elif isinstance(e, MazdaRequestInProgressException):
                self.logger.info(
                    "Request failed because another request was already in progress. Waiting 30 seconds and trying again."
                )
                await asyncio.sleep(30)
                
            # Recursive call WITHOUT the lock still acquired
            return await self.__api_request_retry(
                method,
                uri,
                query_dict,
                body_dict,
                needs_keys,
                needs_auth,
                num_retries + 1,
                priority=priority,
            )
        except asyncio.CancelledError:
            # Handle cancellation by properly releasing the lock
            self.logger.warning(f"Operation {operation_name} was cancelled")
            if lock_acquired:
                self.account_lock.release()
                lock_acquired = False
            raise
        except Exception as e:
            # Release the priority lock for any other exceptions
            self.logger.error(f"Unexpected error in API request: {str(e)}")
            if lock_acquired:
                self.account_lock.release()
                lock_acquired = False
            raise
        finally:
            # Release the priority lock if we haven't already released it
            if lock_acquired and self.account_lock.current_operation == operation_name:
                self.logger.debug(f"Finally block: releasing lock for {operation_name}")
                self.account_lock.release()

    async def __send_api_request(
        self,
        method,
        uri,
        query_dict={},
        body_dict={},
        needs_keys=True,
        needs_auth=False,
    ):
        timestamp = self.__get_timestamp_str_ms()

        original_query_str = ""
        encrypted_query_dict = {}

        if query_dict:
            original_query_str = urlencode(query_dict)
            encrypted_query_dict["params"] = self.__encrypt_payload_using_key(
                original_query_str
            )

        original_body_str = ""
        encrypted_body_Str = ""
        if body_dict:
            original_body_str = json.dumps(body_dict)
            encrypted_body_Str = self.__encrypt_payload_using_key(original_body_str)

        headers = {
            "device-id": self.base_api_device_id,
            "app-code": self.app_code,
            "app-os": APP_OS,
            "user-agent": USER_AGENT_BASE_API,
            "app-version": APP_VERSION,
            "app-unique-id": APP_PACKAGE_ID,
            "access-token": (self.access_token if needs_auth else ""),
            "X-acf-sensor-data": self.sensor_data_builder.generate_sensor_data(),
            "req-id": "req_" + timestamp,
            "timestamp": timestamp,
        }

        if "checkVersion" in uri:
            headers["sign"] = self.__get_sign_from_timestamp(timestamp)
        elif method == "GET":
            headers["sign"] = self.__get_sign_from_payload_and_timestamp(
                original_query_str, timestamp
            )
        elif method == "POST":
            headers["sign"] = self.__get_sign_from_payload_and_timestamp(
                original_body_str, timestamp
            )

        try:
            # Add timeout parameter to prevent indefinite hanging
            # Adjust timeout based on endpoint type
            timeout_seconds = 30  # Default timeout
            
            # Set timeout based on request type
            if "getNickName" in uri:
                timeout_seconds = 15  # Shorter timeout for nickname requests
            elif "getVecBaseInfos" in uri:
                timeout_seconds = 45  # Longer timeout for vehicle base info
            elif "getHealthReport" in uri:
                timeout_seconds = 60  # Even longer timeout for health reports
            elif "doorUnlock" in uri or "doorLock" in uri:
                timeout_seconds = 45  # Longer timeout for door control commands
            
            # Create a client timeout object
            timeout = ClientTimeout(total=timeout_seconds)
            
            response = await self._session.request(
                method,
                self.base_url + uri,
                headers=headers,
                data=encrypted_body_Str,
                ssl=ssl_context,
                timeout=timeout
            )

            response_json = await response.json()

            if response_json.get("state") == "S":
                if "checkVersion" in uri:
                    return self.__decrypt_payload_using_app_code(response_json["payload"])
                else:
                    decrypted_payload = self.__decrypt_payload_using_key(
                        response_json["payload"]
                    )
                    if "getHealthReport" in uri:
                        try:
                            if isinstance(decrypted_payload, dict):
                                healthReportData = decrypted_payload.get("healthReportData", {})
                                vhcle = healthReportData.get("vhcle", {})
                                reportDate = vhcle.get("reportDate", "Unknown")
                                reportItems = vhcle.get("reportItems", [])
                                self.logger.debug(
                                    f"Health report response for date {reportDate}: contains {len(reportItems)} report items"
                                )
                                # Log the keys of the first few report items for debugging
                                if reportItems and len(reportItems) > 0:
                                    item_keys = []
                                    for i, item in enumerate(reportItems[:3]):  # Log first 3 items
                                        item_keys.append(f"Item {i+1}: {list(item.keys())}")
                                    self.logger.debug(f"Sample report items: {', '.join(item_keys)}")
                        except (AttributeError, KeyError, TypeError, ValueError, IndexError) as e:
                            self.logger.debug(f"Error parsing health report for detailed logging: {e}")
                    
                    self.logger.debug("Response payload: %s", decrypted_payload)
                    return decrypted_payload
            elif response_json.get("errorCode") == 600001:
                raise MazdaAPIEncryptionException("Server rejected encrypted request")
            elif response_json.get("errorCode") == 600002:
                raise MazdaTokenExpiredException("Token expired")
            elif (
                response_json.get("errorCode") == 920000
                and response_json.get("extraCode") == "400S01"
            ):
                raise MazdaRequestInProgressException(
                    "Request already in progress, please wait and try again"
                )
            elif (
                response_json.get("errorCode") == 920000
                and response_json.get("extraCode") == "400S11"
            ):
                raise MazdaException(
                    "The engine can only be remotely started 2 consecutive times. Please drive the vehicle to reset the counter."
                )
            elif "error" in response_json:
                raise MazdaException("Request failed: " + response_json["error"])
            else:
                raise MazdaException("Request failed for an unknown reason")
        except (ServerDisconnectedError, ClientConnectorError, ClientOSError) as e:
            self.logger.error(f"Connection error during API request to {uri}: {str(e)}")
            raise  # Re-raise for the retry mechanism to handle

    async def __ensure_keys_present(self):
        if self.enc_key is None or self.sign_key is None:
            await self.__retrieve_keys()

    async def __ensure_token_is_valid(self):
        if self.access_token is None or self.access_token_expiration_ts is None:
            self.logger.info("No access token present. Logging in.")
        elif self.access_token_expiration_ts <= time.time():
            self.logger.info("Access token is expired. Fetching a new one.")
            self.access_token = None
            self.access_token_expiration_ts = None

        if (
            self.access_token is None
            or self.access_token_expiration_ts is None
            or self.access_token_expiration_ts <= time.time()
        ):
            await self.login()

    async def __retrieve_keys(self):
        self.logger.info("Retrieving encryption keys")
        response = await self.api_request(
            "POST", "service/checkVersion", needs_keys=False, needs_auth=False
        )
        self.logger.info("Successfully retrieved encryption keys")

        self.enc_key = response["encKey"]
        self.sign_key = response["signKey"]

    async def login(self, priority=RequestPriority.HEALTH_REPORT):  # noqa: D102
        """Login to the Mazda API."""
        try:
            # Acquire the lock first
            await self.account_lock.acquire(priority, "login")
            
            self.logger.info("Logging in as " + self.email)  # noqa: G003
            self.logger.info("Retrieving public key to encrypt password")
            encryption_key_response = await self._session.request(
                "GET",
                self.usher_url + "system/encryptionKey",
                params={
                    "appId": "MazdaApp",
                    "locale": "en-US",
                    "deviceId": self.usher_api_device_id,
                    "sdkVersion": USHER_SDK_VERSION,
                },
                headers={"User-Agent": USER_AGENT_USHER_API},
                ssl=ssl_context,
            )

            encryption_key_response_json = await encryption_key_response.json()

            public_key = encryption_key_response_json["data"]["publicKey"]
            encrypted_password = self.__encrypt_payload_with_public_key(
                self.password, public_key
            )
            version_prefix = encryption_key_response_json["data"]["versionPrefix"]

            self.logger.info("Sending login request")
            login_response = await self._session.request(
                "POST",
                self.usher_url + "user/login",
                headers={"User-Agent": USER_AGENT_USHER_API},
                json={
                    "appId": "MazdaApp",
                    "deviceId": self.usher_api_device_id,
                    "locale": "en-US",
                    "password": version_prefix + encrypted_password,
                    "sdkVersion": USHER_SDK_VERSION,
                    "userId": self.email,
                    "userIdType": "email",
                },
                ssl=ssl_context,
            )

            login_response_json = await login_response.json()

            if login_response_json.get("status") == "INVALID_CREDENTIAL":
                self.logger.error("Login failed due to invalid email or password")
                raise MazdaAuthenticationException("Invalid email or password")
            if login_response_json.get("status") == "USER_LOCKED":
                self.logger.error("Login failed to account being locked")
                raise MazdaAccountLockedException("Account is locked")
            if login_response_json.get("status") != "OK":
                self.logger.error(
                    "Login failed"  # noqa: G003
                    + (
                        (": " + login_response_json.get("status", ""))
                        if ("status" in login_response_json)
                        else ""
                    )
                )
                raise MazdaLoginFailedException("Login failed")

            self.logger.info("Successfully logged in as " + self.email)  # noqa: G003
            self.access_token = login_response_json["data"]["accessToken"]
            self.access_token_expiration_ts = login_response_json["data"][
                "accessTokenExpirationTs"
            ]
        finally:
            # Always release the lock, even if there's an exception
            if self.account_lock.current_operation == "login":
                self.account_lock.release()

    async def close(self):  # noqa: D102
        await self._session.close()
