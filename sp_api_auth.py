import logging
import threading
import time
from enum import Enum
from typing import Any, Optional

import requests
from sp_api.auth.access_token_response import AccessTokenResponse


logger = logging.getLogger(__name__)


class LwaExceptionErrorCode(str, Enum):
    ACCESS_DENIED = "access_denied"
    INVALID_CLIENT = "invalid_client"
    INVALID_GRANT = "invalid_grant"
    INVALID_REQUEST = "invalid_request"
    INVALID_SCOPE = "invalid_scope"
    SERVER_ERROR = "server_error"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    UNAUTHORIZED_CLIENT = "unauthorized_client"
    OTHER = "other"


class SPAPIConfig:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        region: str = "SANDBOX",
        access_token: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.region = region
        self.scope = scope
        self.access_token = access_token

    @classmethod
    def from_credentials(cls, credentials: dict[str, Any]) -> "SPAPIConfig":
        refresh_token = credentials.get("refresh_token")
        lwa_app_id = credentials.get("lwa_app_id")
        lwa_client_secret = credentials.get("lwa_client_secret")
        missing_fields = [
            field_name
            for field_name, field_value in {
                "refresh_token": refresh_token,
                "lwa_app_id": lwa_app_id,
                "lwa_client_secret": lwa_client_secret,
            }.items()
            if not field_value
        ]
        if missing_fields:
            raise LwaException(
                error_code=LwaExceptionErrorCode.INVALID_REQUEST.value,
                error_message=(
                    "Missing SP-API Login With Amazon credentials: "
                    + ", ".join(missing_fields)
                ),
                cause={"missing_fields": missing_fields},
            )
        return cls(
            client_id=lwa_app_id,
            client_secret=lwa_client_secret,
            refresh_token=refresh_token,
            region=credentials.get("region", "SANDBOX"),
            access_token=credentials.get("access_token"),
            scope=credentials.get("scope"),
        )


class LwaException(Exception):
    def __init__(self, error_code, error_message, cause=None):
        super().__init__(f"LWA Error - Code {error_code}, Message: {error_message}")
        self.error_code = error_code.value if isinstance(error_code, LwaExceptionErrorCode) else error_code
        self.error_message = error_message
        self.cause = cause

    def __str__(self):
        cause_str = f", Cause: {self.cause}" if self.cause else ""
        return f"LWA Error - Code: {self.error_code}, Message: {self.error_message}{cause_str}"

    def get_error_code(self):
        return self.error_code

    def get_error_message(self):
        return self.error_message

    @property
    def error_code_string(self) -> str:
        return str(self.error_code)

    @property
    def description(self) -> str:
        return self.error_message

    @property
    def tracking_data(self) -> dict[str, Any]:
        return self.cause if isinstance(self.cause, dict) else {"cause": self.cause} if self.cause else {}


def map_lwa_error_code(error_code: Optional[str]) -> LwaExceptionErrorCode:
    normalized_error_code = (error_code or "").strip().lower()
    return {
        LwaExceptionErrorCode.ACCESS_DENIED.value: LwaExceptionErrorCode.ACCESS_DENIED,
        LwaExceptionErrorCode.INVALID_CLIENT.value: LwaExceptionErrorCode.INVALID_CLIENT,
        LwaExceptionErrorCode.INVALID_GRANT.value: LwaExceptionErrorCode.INVALID_GRANT,
        LwaExceptionErrorCode.INVALID_REQUEST.value: LwaExceptionErrorCode.INVALID_REQUEST,
        LwaExceptionErrorCode.INVALID_SCOPE.value: LwaExceptionErrorCode.INVALID_SCOPE,
        LwaExceptionErrorCode.SERVER_ERROR.value: LwaExceptionErrorCode.SERVER_ERROR,
        LwaExceptionErrorCode.TEMPORARILY_UNAVAILABLE.value: LwaExceptionErrorCode.TEMPORARILY_UNAVAILABLE,
        LwaExceptionErrorCode.UNAUTHORIZED_CLIENT.value: LwaExceptionErrorCode.UNAUTHORIZED_CLIENT,
    }.get(normalized_error_code, LwaExceptionErrorCode.OTHER)


class AccessTokenCache:
    token_url = "https://api.amazon.com/auth/o2/token"

    def __init__(
        self,
        max_retries: int = 3,
        refresh_token: Optional[str] = None,
        credentials: Optional[dict[str, Any]] = None,
        proxies: Any = None,
        verify: bool = True,
    ) -> None:
        self._cached_token: Optional[str] = None
        self._expires_at = 0.0
        self._lock = threading.Lock()
        self._verify = verify
        self._refresh_token = refresh_token
        self._credentials = credentials or {}
        self._proxies = proxies
        self.max_retries = max_retries
        self.token_info: Optional[dict[str, Any]] = None

    def get_lwa_access_token(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        grant_type: str = "refresh_token",
        scope: Optional[str] = None,
        config: Optional[SPAPIConfig] = None,
    ) -> str:
        effective_config = config or self._build_config_from_defaults()
        client_id = client_id or effective_config.client_id
        client_secret = client_secret or effective_config.client_secret
        refresh_token = refresh_token or effective_config.refresh_token
        scope = scope or effective_config.scope

        if self.token_info and time.time() < self.token_info["expires_at"]:
            self._cached_token = self.token_info["access_token"]
            self._expires_at = self.token_info["expires_at"]
            return self._cached_token

        with self._lock:
            if self.token_info and time.time() < self.token_info["expires_at"]:
                self._cached_token = self.token_info["access_token"]
                self._expires_at = self.token_info["expires_at"]
                return self._cached_token

            access_token = self.request_new_token(
                client_id,
                client_secret,
                refresh_token,
                grant_type,
                scope,
            )
            self._cached_token = access_token
            self._expires_at = self.token_info["expires_at"] if self.token_info else 0.0
            return access_token

    def get_auth(self) -> AccessTokenResponse:
        access_token = self.get_lwa_access_token()
        return AccessTokenResponse(
            access_token=access_token,
            expires_in=max(int(self._expires_at - time.time()), 0),
            token_type="bearer",
            refresh_token=self._refresh_token,
        )

    def _build_config_from_defaults(self) -> SPAPIConfig:
        credentials = dict(self._credentials)
        if self._refresh_token and not credentials.get("refresh_token"):
            credentials["refresh_token"] = self._refresh_token
        return SPAPIConfig.from_credentials(credentials)

    def request_new_token(self, client_id, client_secret, refresh_token, grant_type, scope):
        self.validate_token_request(grant_type, refresh_token, scope)
        data = self.prepare_token_request_data(
            client_id,
            client_secret,
            refresh_token,
            grant_type,
            scope,
        )

        retries = 0
        while retries <= self.max_retries:
            try:
                response = requests.post(
                    self.token_url,
                    data=data,
                    timeout=30,
                    proxies=self._proxies,
                    verify=self._verify,
                )
                response.raise_for_status()
                token_response = response.json()
                token_response["expires_at"] = time.time() + token_response.get("expires_in", 1800) - 30
                self.token_info = token_response
                logger.debug("Retrieved SP-API LWA access token")
                return token_response["access_token"]
            except requests.RequestException as exc:
                status_code = exc.response.status_code if exc.response else None
                error_code = self.map_http_status_to_lwa_exception_code(status_code)
                if retries < self.max_retries and self.is_retriable(error_code):
                    retries += 1
                    time.sleep(2 ** retries)
                    continue

                error_message = self.format_error_message(exc)
                logger.error(error_message)
                raise LwaException(error_code, error_message, cause={
                    "response_status_code": status_code,
                    "response_body": exc.response.text if exc.response else None,
                }) from exc

        raise LwaException(
            LwaExceptionErrorCode.OTHER.value,
            "Token request exhausted retries without returning an access token.",
        )

    def validate_token_request(self, grant_type, refresh_token, scope):
        if grant_type == "refresh_token" and not refresh_token:
            raise LwaException(
                LwaExceptionErrorCode.INVALID_REQUEST.value,
                "Refresh token must be provided for grant_type 'refresh_token'",
            )
        if grant_type == "client_credentials" and not scope:
            raise LwaException(
                LwaExceptionErrorCode.INVALID_SCOPE.value,
                "Scope must be provided for grant_type 'client_credentials'",
            )

    def prepare_token_request_data(self, client_id, client_secret, refresh_token, grant_type, scope):
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": grant_type,
        }
        if grant_type == "refresh_token":
            if not refresh_token:
                raise LwaException(
                    LwaExceptionErrorCode.INVALID_REQUEST.value,
                    "Refresh token must be provided for grant_type 'refresh_token'",
                )
            data["refresh_token"] = refresh_token
        elif grant_type == "client_credentials":
            if not scope:
                raise LwaException(
                    LwaExceptionErrorCode.INVALID_SCOPE.value,
                    "Scope must be provided for grant_type 'client_credentials'",
                )
            data["scope"] = scope
        return data

    def is_retriable(self, error_code):
        retriable_codes = [
            LwaExceptionErrorCode.SERVER_ERROR.value,
            LwaExceptionErrorCode.TEMPORARILY_UNAVAILABLE.value,
        ]
        return error_code in retriable_codes

    def format_error_message(self, exc):
        return (
            f"Token request failed with status code {exc.response.status_code}: {exc.response.text}"
            if exc.response
            else f"Token request failed: {exc}"
        )

    def map_http_status_to_lwa_exception_code(self, status_code):
        if status_code is None:
            return LwaExceptionErrorCode.SERVER_ERROR.value
        if status_code == 400:
            return LwaExceptionErrorCode.INVALID_REQUEST.value
        if status_code == 401:
            return LwaExceptionErrorCode.UNAUTHORIZED_CLIENT.value
        if status_code == 403:
            return LwaExceptionErrorCode.ACCESS_DENIED.value
        if status_code == 500:
            return LwaExceptionErrorCode.SERVER_ERROR.value
        if status_code == 503:
            return LwaExceptionErrorCode.TEMPORARILY_UNAVAILABLE.value
        return LwaExceptionErrorCode.OTHER.value