"""Bounded, read-only XProtect Events & State subscription with resume support."""
import json
import time
from collections import deque

from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from .model import guid, iso, utc
from .xprotect import APIError


def event_metadata(event):
    """Allowlist output; never log arbitrary server data, headers or error bodies."""
    source = event.get("source", "")
    if not isinstance(source, str) or "/" not in source:
        raise ValueError("Expected scoped event source")
    resource, source_id = source.split("/", 1)
    if resource not in {"cameras", "userDefinedEvents"}:
        raise ValueError("Unexpected event resource")
    return {"id": guid(event.get("id")), "type": guid(event.get("type")),
            "source": resource + "/" + guid(source_id),
            "time": iso(utc(event.get("time"))), "provenance": "xprotect_event_observed"}


class EventWatcher:
    def __init__(self, client, camera_id, event_types, *, user_event_ids=(), connector=connect, sleep=time.sleep):
        self.client, self.connector, self.sleep = client, connector, sleep
        self.camera_id = guid(camera_id)
        self.event_types = [guid(t) for t in event_types]
        self.user_event_ids = [guid(t) for t in user_event_ids]
        if not self.event_types:
            raise ValueError("At least one explicit event type is required")
        self.session_id, self.last_id = "", ""
        self.command_id = 0
        self.seen, self.seen_order = set(), deque()

    def _events(self, message, emit):
        events = message.get("events", [])
        if not isinstance(events, list):
            raise APIError("websocket_event_schema_mismatch")
        for event in events:
            try:
                clean = event_metadata(event)
            except (ValueError, AttributeError, TypeError):
                continue
            # Never trust the remote subscription alone for camera scoping.
            is_camera = clean["source"] == f"cameras/{self.camera_id}" and clean["type"] in self.event_types
            is_user_event = clean["source"] in {f"userDefinedEvents/{e}" for e in self.user_event_ids} and clean["type"] in self.user_event_ids
            if not (is_camera or is_user_event):
                continue
            if clean["id"] not in self.seen:
                emit(clean)
                self.seen.add(clean["id"])
                self.seen_order.append(clean["id"])
                if len(self.seen_order) > 4096:
                    self.seen.remove(self.seen_order.popleft())
            self.last_id = clean["id"]

    def _receive(self, ws, timeout):
        try:
            data = json.loads(ws.recv(timeout=timeout))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, UnicodeError):
            raise APIError("websocket_invalid_json") from None

    def _command(self, ws, command, emit, deadline, **fields):
        self.command_id += 1
        current_id = self.command_id
        ws.send(json.dumps({"command": command, "commandId": current_id, **fields}))
        command_deadline = min(deadline, time.monotonic() + 10)
        while time.monotonic() < command_deadline:
            msg = self._receive(ws, max(0.01, command_deadline-time.monotonic()))
            self._events(msg, emit)
            if msg.get("commandId") == current_id:
                if msg.get("status") not in (200, 201):
                    raise APIError("websocket_command_rejected", msg.get("status"))
                return msg
        raise TimeoutError

    def watch(self, emit, *, duration=120, reconnects=3):
        if not 1 <= duration <= 600 or not 0 <= reconnects <= 5:
            raise ValueError("Watch duration is 1..600 seconds; reconnects 0..5")
        deadline = time.monotonic() + duration
        url = self.client.base_url.replace("https://", "wss://").replace("http://", "ws://")
        url += "/api/ws/events/v1"
        for attempt in range(reconnects + 1):
            if time.monotonic() >= deadline:
                return
            try:
                with self.connector(url,
                        additional_headers={"Authorization": f"Bearer {self.client.token()}"},
                        ssl=self.client.ssl_context if url.startswith("wss:") else None,
                        proxy=None, open_timeout=min(10, max(.1, deadline-time.monotonic())),
                        close_timeout=2, max_size=1_048_576, max_queue=16) as ws:
                    msg = self._command(ws, "startSession", emit, deadline,
                                        sessionId=self.session_id, eventId=self.last_id)
                    new_id = guid(msg.get("sessionId"))
                    if msg["status"] == 201 or new_id != self.session_id:
                        if self.session_id:
                            emit({"status": "new_session_after_disconnect",
                                  "provenance": "observer_gap_possible",
                                  "note": "Use retained event history to reconcile any gap"})
                        self.session_id, self.last_id = new_id, ""
                        filters = [{
                            "modifier": "include", "resourceTypes": ["cameras"],
                            "sourceIds": [self.camera_id], "eventTypes": self.event_types}]
                        if self.user_event_ids:
                            filters.append({"modifier": "include", "resourceTypes": ["userDefinedEvents"],
                                            "sourceIds": self.user_event_ids, "eventTypes": self.user_event_ids})
                        self._command(ws, "addSubscription", emit, deadline, filters=filters)
                    while time.monotonic() < deadline:
                        try:
                            msg = self._receive(ws, min(5, max(.01, deadline-time.monotonic())))
                            self._events(msg, emit)
                        except TimeoutError:
                            continue
                    return
            except InvalidStatus as exc:
                status = exc.response.status_code
                if status in (401, 403) or 300 <= status < 400:
                    raise APIError("websocket_auth_or_redirect_rejected", status) from None
            except ConnectionClosed as exc:
                if exc.rcvd and exc.rcvd.code in (1002, 1008):
                    raise APIError("websocket_policy_rejected") from None
            except (OSError, TimeoutError, InvalidHandshake):
                pass
            if attempt == reconnects:
                raise APIError("websocket_reconnects_exhausted")
            self.sleep(min(2 ** attempt, max(0, deadline-time.monotonic())))
