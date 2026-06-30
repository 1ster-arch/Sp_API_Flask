import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import requests

import main
import sp_api_client
from sp_api_auth import AccessTokenCache, LwaException, LwaExceptionErrorCode, map_lwa_error_code


class MockResponse:
    def __init__(self, status_code, body=None, text=""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.original_credentials = dict(sp_api_client.SP_API_CREDENTIALS)
        sp_api_client.token_cache._cached_token = None
        sp_api_client.token_cache._expires_at = 0.0

    def tearDown(self):
        sp_api_client.SP_API_CREDENTIALS.clear()
        sp_api_client.SP_API_CREDENTIALS.update(self.original_credentials)
        sp_api_client.token_cache._cached_token = None
        sp_api_client.token_cache._expires_at = 0.0

    def test_map_lwa_error_code_uses_enum_with_correct_casing(self):
        self.assertEqual(
            map_lwa_error_code("invalid_grant"),
            LwaExceptionErrorCode.INVALID_GRANT,
        )
        self.assertEqual(
            map_lwa_error_code("INVALID_CLIENT"),
            LwaExceptionErrorCode.INVALID_CLIENT,
        )

    def test_fetch_product_returns_structured_401_for_missing_lwa_credentials(self):
        with patch.dict(
            sp_api_client.SP_API_CREDENTIALS,
            {
                "refresh_token": None,
                "lwa_app_id": None,
                "lwa_client_secret": None,
            },
            clear=False,
        ):
            response = self.client.post("/api/fetch/TESTASIN")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "invalid_request",
                    "description": "Missing SP-API Login With Amazon credentials: refresh_token, lwa_app_id, lwa_client_secret",
                }
            },
        )

    def test_request_new_token_retries_server_error_then_succeeds(self):
        token_cache = AccessTokenCache(max_retries=2)
        responses = [
            MockResponse(500, text="temporary failure"),
            MockResponse(200, body={"access_token": "token-123", "expires_in": 3600}),
        ]

        with patch("sp_api_auth.requests.post", side_effect=responses) as mock_post:
            with patch("sp_api_auth.time.sleep") as mock_sleep:
                access_token = token_cache.request_new_token(
                    client_id="client-id",
                    client_secret="client-secret",
                    refresh_token="refresh-token",
                    grant_type="refresh_token",
                    scope=None,
                )

        self.assertEqual(access_token, "token-123")
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(2)
        self.assertEqual(token_cache.token_info["access_token"], "token-123")

    def test_request_new_token_maps_http_status_to_lwa_exception_code(self):
        token_cache = AccessTokenCache(max_retries=0)

        with patch(
            "sp_api_auth.requests.post",
            return_value=MockResponse(403, text="denied"),
        ):
            with self.assertRaises(LwaException) as exc_info:
                token_cache.request_new_token(
                    client_id="client-id",
                    client_secret="client-secret",
                    refresh_token="refresh-token",
                    grant_type="refresh_token",
                    scope=None,
                )

        self.assertEqual(exc_info.exception.get_error_code(), LwaExceptionErrorCode.ACCESS_DENIED.value)
        self.assertIn("status code 403", exc_info.exception.get_error_message())


if __name__ == "__main__":
    unittest.main()