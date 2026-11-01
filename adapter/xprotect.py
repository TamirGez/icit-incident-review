import json
import ssl
import time
from urllib.parse import urlsplit, urljoin

import httpx

from .model import guid


class APIError(Exception):
    def __init__(self, code, status=None, receipt=None):
        self.code, self.status, self.receipt = code, status, receipt
        super().__init__(f"{code}" + (f" (HTTP {status})" if status else ""))


def validate_base_url(url, allow_tailnet_http=False):
    p = urlsplit(url)
    # This connector is deliberately restricted to the assigned primary lab.
    schemes = {"https", "http"} if allow_tailnet_http else {"https"}
    if p.hostname != "p042" or p.scheme not in schemes or p.port is not None:
        raise ValueError("Use https://p042; HTTP requires the explicit lab-tailnet option")
    if p.username or p.password or p.query or p.fragment or p.path not in ("", "/"):
        raise ValueError("Base URL must be an origin without credentials or paths")
    return url.rstrip("/")


class XProtect:
    def __init__(self, base_url, username, password, *, ca_file=None,
                 transport=None, sleep=time.sleep, allow_tailnet_http=False):
        self.base_url = validate_base_url(base_url, allow_tailnet_http)
        if not username or not password:
            raise ValueError("Scoped XProtect username and password are required")
        if "administrator" in username.casefold():
            raise ValueError("Use a scoped XProtect basic user, not Administrator")
        self.username, self._password = username, password
        self._token = None
        self._expires = 0
        self.sleep = sleep
        self.ssl_context = ssl.create_default_context(cafile=ca_file)
        self.http = httpx.Client(base_url=self.base_url, verify=self.ssl_context,
                                 trust_env=False, follow_redirects=False,
                                 timeout=15, transport=transport)

    def close(self):
        self.http.close()

    def _json(self, response):
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, UnicodeError):
            raise APIError("invalid_json_response") from None

    def token(self, force=False):
        if not force and self._token and time.monotonic() < self._expires:
            return self._token
        try:
            r = self.http.post("/API/IDP/connect/token", data={
                "grant_type": "password", "client_id": "GrantValidatorClient",
                "username": self.username, "password": self._password})
        except httpx.HTTPError:
            raise APIError("authentication_transport_error") from None
        if r.status_code != 200:
            raise APIError("authentication_rejected", r.status_code)
        body = self._json(r)
        token = body.get("access_token")
        if not isinstance(token, str) or not token or any(c in token for c in "\r\n"):
            raise APIError("invalid_token_response")
        try:
            ttl = max(0, min(float(body.get("expires_in", 300)), 3600) - 30)
        except (TypeError, ValueError):
            raise APIError("invalid_token_expiry") from None
        self._token, self._expires = token, time.monotonic() + ttl
        return token

    def request(self, method, path, **kwargs):
        absolute = urljoin(self.base_url + "/", path)
        p = urlsplit(absolute)
        if (p.scheme, p.netloc) != (urlsplit(self.base_url).scheme, "p042") or not p.path.startswith("/api/rest/v1/"):
            raise APIError("unsafe_api_link")
        refreshed = False
        for attempt in range(3):
            try:
                r = self.http.request(method, absolute,
                                      headers={"Authorization": f"Bearer {self.token()}"}, **kwargs)
            except httpx.HTTPError:
                if method == "GET" and attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                raise APIError("transport_error_outcome_unknown" if method != "GET" else "transport_error") from None
            if r.status_code == 401 and method == "GET" and not refreshed and attempt < 2:
                self.token(force=True)
                refreshed = True
                continue
            if method == "GET" and r.status_code in (429, 502, 503, 504) and attempt < 2:
                try:
                    delay = min(30, max(2 ** attempt, float(r.headers.get("Retry-After", 0))))
                except ValueError:
                    delay = 2 ** attempt
                self.sleep(delay)
                continue
            if not 200 <= r.status_code < 300:
                raise APIError("request_rejected", r.status_code)
            return r
        raise APIError("read_retries_exhausted")

    def inventory(self, resource):
        if resource not in {"cameras", "eventTypes", "userDefinedEvents"}:
            raise ValueError("Unsupported inventory resource")
        path = f"/api/rest/v1/{resource}"
        seen, rows = set(), []
        for _ in range(20):
            if path in seen:
                raise APIError("pagination_loop")
            seen.add(path)
            data = self._json(self.request("GET", path))
            batch = data.get("array")
            if not isinstance(batch, list) or any(not isinstance(r, dict) for r in batch):
                raise APIError("inventory_schema_mismatch")
            rows.extend(batch)
            links = data.get("_links", {})
            next_link = links.get("next") if isinstance(links, dict) else None
            if not next_link:
                return rows
            if not isinstance(next_link, str):
                raise APIError("pagination_schema_mismatch")
            path = urljoin(urljoin(self.base_url, path), next_link)
            next_url = urlsplit(path)
            if next_url.path != f"/api/rest/v1/{resource}" or next_url.fragment:
                raise APIError("unsafe_pagination_link")
        raise APIError("pagination_limit")

    def check_mapping(self, camera_id, event_type_id):
        if not any(r.get("id", "").lower() == camera_id for r in self.inventory("cameras")):
            raise APIError("camera_not_available")
        event = next((r for r in self.inventory("userDefinedEvents")
                      if r.get("id", "").lower() == event_type_id), None)
        if event is None:
            raise APIError("event_type_not_available")
        if not str(event.get("name") or event.get("displayName", "")).startswith("ICIT_TEST_"):
            raise APIError("test_event_name_must_start_ICIT_TEST_")

    def trigger(self, payload):
        # Never retry a POST. A timeout can occur after the rule already fired.
        r = self.request("POST", "/api/rest/v1/events", json=payload)
        if r.status_code != 202:
            raise APIError("unexpected_trigger_response", r.status_code)
        body = self._json(r)
        try:
            event_id = body["data"]["id"]
            # Verified on p042: accepted UDE responses use a zero UUID. The
            # real ID arrives over WebSocket; never fabricate or retry one.
            if event_id == "00000000-0000-0000-0000-000000000000":
                return None
            return guid(event_id)
        except (KeyError, TypeError, ValueError):
            data = body.get("data")
            event_id = data.get("id") if isinstance(data, dict) else None
            # Schema diagnostics only: never expose arbitrary server values.
            receipt = {"data_present": "data" in body,
                       "data_is_null": data is None,
                       "data_is_object": isinstance(data, dict),
                       "id_present": isinstance(data, dict) and "id" in data,
                       "id_is_null": event_id is None,
                       "id_is_zero": event_id == "00000000-0000-0000-0000-000000000000"}
            raise APIError("accepted_without_valid_event_id", receipt=receipt) from None

    def event(self, event_id):
        data = self._json(self.request("GET", f"/api/rest/v1/events/{guid(event_id)}"))
        return data.get("data", {})
