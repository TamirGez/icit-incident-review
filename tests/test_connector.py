"""Protocol and request-safety tests using synthetic fixtures."""
import contextlib
import io
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
from websockets.sync.server import serve
from websockets.sync.client import connect as real_connect
from websockets.exceptions import ConnectionClosed

from adapter.__main__ import main
from adapter.access import lab_access
from adapter.ledger import Ledger, Suppressed
from adapter.model import Trigger, UTC, PROMPTS, guid, iso, utc
from adapter.service import submit
from adapter.stream import EventWatcher, event_metadata
from adapter.xprotect import XProtect, APIError, validate_base_url

CAMERA = "11111111-1111-4111-8111-111111111111"
TYPE = "22222222-2222-4222-8222-222222222222"
REMOTE = "33333333-3333-4333-8333-333333333333"
SESSION = "44444444-4444-4444-8444-444444444444"
NOW = datetime(2026, 11, 1, 20, 0, tzinfo=UTC)


def trigger(**changes):
    return replace(Trigger(str(uuid4()), CAMERA, iso(NOW-timedelta(seconds=30)), "manual"), **changes)


def config(scenario="person_on_railway_tracks"):
    return {"base_url": "https://p042", "remote_setup_approved": True,
            "gateway_contract_verified": True, "camera_id": CAMERA,
            "trigger_event_type_id": TYPE, "scenario": scenario,
            "gateway_prompt": PROMPTS[scenario], "before_seconds": 20,
            "after_seconds": 10, "daily_test_cap": 10, "cooldown_seconds": 120,
            "event_time_basis": "server_receipt"}


class ModelTests(unittest.TestCase):
    def test_all_three_scenarios_and_documented_payload(self):
        for label, prompt in PROMPTS.items():
            with self.subTest(label=label):
                t = trigger(label=label, prompt=prompt)
                self.assertEqual(t.payload(TYPE), {"type": TYPE,
                    "datatype": "none",
                    "tag": f"icit-hackathon:manual:{t.event_id}"})
                t.validate_recording_window(NOW)

    def test_timezone_normalization(self):
        self.assertEqual(utc("2026-11-01T22:00:00+02:00"), NOW)

    def test_native_live_time_rejects_historical_or_future_trigger(self):
        for delta in (-31, 3):
            with self.assertRaises(ValueError):
                trigger(timestamp_utc=iso(NOW+timedelta(seconds=delta))).validate_live_request(NOW)
        trigger(timestamp_utc=iso(NOW)).validate_live_request(NOW)

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            utc("2026-11-01T20:00:00")

    def test_expired_recording_rejected(self):
        with self.assertRaisesRegex(ValueError, "23-hour"):
            trigger(timestamp_utc=iso(NOW-timedelta(hours=24))).validate_recording_window(NOW)

    def test_incomplete_recording_rejected(self):
        with self.assertRaisesRegex(ValueError, "fully recorded"):
            trigger(timestamp_utc=iso(NOW)).validate_recording_window(NOW)

    def test_prompt_and_scenario_must_match(self):
        with self.assertRaises(ValueError):
            trigger(label="blocked_sidewalk")

    def test_zero_guid_rejected(self):
        with self.assertRaises(ValueError):
            guid("00000000-0000-0000-0000-000000000000")

    def test_clip_range_rejected(self):
        for changes in ({"before_seconds": -1}, {"after_seconds": 60}, {"after_seconds": True}):
            with self.assertRaises(ValueError):
                trigger(**changes)



class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/"ledger.sqlite3"
        self.ledger = Ledger(self.path)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def accepted(self, t, now=NOW, **kwargs):
        self.ledger.reserve(t, now, **kwargs)
        self.ledger.finish(t.event_id, "xprotect_accepted", REMOTE)

    def test_duplicate_survives_restart(self):
        t = trigger()
        self.accepted(t)
        self.ledger.close()
        self.ledger = Ledger(self.path)
        with self.assertRaisesRegex(Suppressed, "duplicate"):
            self.ledger.reserve(t, NOW+timedelta(minutes=3))

    def test_loop_cooldown_uses_wall_time(self):
        self.accepted(trigger())
        with self.assertRaisesRegex(Suppressed, "cooldown"):
            self.ledger.reserve(trigger(timestamp_utc=iso(NOW-timedelta(hours=1))), NOW+timedelta(seconds=15))

    def test_daily_cap_and_utc_reset(self):
        self.accepted(trigger(), daily_cap=1)
        with self.assertRaisesRegex(Suppressed, "daily_test_cap"):
            self.ledger.reserve(trigger(), NOW+timedelta(minutes=3), daily_cap=1)
        self.ledger.reserve(trigger(), NOW+timedelta(days=1), daily_cap=1)

    def test_crash_reservation_requires_review(self):
        self.ledger.reserve(trigger(), NOW)
        with self.assertRaisesRegex(Suppressed, "unfinished_attempt"):
            self.ledger.reserve(trigger(), NOW+timedelta(hours=1))
        self.ledger.resume()
        self.ledger.reserve(trigger(), NOW+timedelta(hours=1))

    def test_second_connection_observes_reservation(self):
        self.ledger.reserve(trigger(), NOW)
        other = Ledger(self.path)
        try:
            with self.assertRaises(Suppressed):
                other.reserve(trigger(), NOW)
        finally:
            other.close()

    def test_no_unbounded_quota_or_short_cooldown(self):
        for kwargs in ({"daily_cap": 500}, {"daily_cap": 1.5}, {"cooldown": 15}):
            with self.assertRaises(ValueError):
                self.ledger.reserve(trigger(), NOW, **kwargs)

    def test_private_ledger_permissions(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.requests, self.sleeps = [], []
        self.status, self.cameras, self.post_timeout = 202, True, False
        self.post_body = {"data": {"id": REMOTE}}
        self.client = XProtect("https://p042", "scoped-demo", "test & password+",
                              transport=httpx.MockTransport(self.handle), sleep=self.sleeps.append)

    def tearDown(self):
        self.client.close()

    def handle(self, req):
        self.requests.append(req)
        if req.url.path == "/API/IDP/connect/token":
            return httpx.Response(200, json={"access_token": "SYNTHETIC_TOKEN", "expires_in": 300})
        if req.url.path.endswith("/cameras"):
            return httpx.Response(200, json={"array": [{"id": CAMERA, "displayName": "Test"}] if self.cameras else []})
        if req.url.path.endswith(("/eventTypes", "/userDefinedEvents")):
            return httpx.Response(200, json={"array": [{"id": TYPE, "displayName": "ICIT_TEST_RAIL",
                                                        "generatorType": "External"}]})
        if req.method == "POST":
            if self.post_timeout:
                raise httpx.ReadTimeout("secret server content must not be logged")
            return httpx.Response(self.status, json=self.post_body)
        return httpx.Response(200, json={"data": {}})

    def test_form_encoded_idp_token_and_bearer(self):
        self.client.inventory("cameras")
        body = parse_qs(self.requests[0].content.decode())
        self.assertEqual(body["password"], ["test & password+"])
        self.assertEqual(body["grant_type"], ["password"])
        self.assertEqual(body["client_id"], ["GrantValidatorClient"])
        self.assertNotIn("authorization", self.requests[0].headers)
        self.assertEqual(self.requests[1].headers["Authorization"], "Bearer SYNTHETIC_TOKEN")

    def test_admin_and_unassigned_host_rejected(self):
        for url in ("https://p020", "https://example.com", "https://p042@evil.test", "http://p042"):
            with self.assertRaises(ValueError):
                validate_base_url(url)
        with self.assertRaises(ValueError):
            XProtect("https://p042", "p042\\Administrator", "test")

    def test_explicit_lab_http_option(self):
        self.assertEqual(validate_base_url("http://p042", True), "http://p042")

    def test_external_pagination_refused_before_request(self):
        self.client.http.close()
        def handler(req):
            if "token" in req.url.path:
                return self.handle(req)
            self.requests.append(req)
            return httpx.Response(200, json={"array": [], "_links": {"next": "https://evil.test/api/rest/v1/cameras"}})
        self.client.http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://p042")
        with self.assertRaisesRegex(APIError, "unsafe_api_link"):
            self.client.inventory("cameras")
        self.assertTrue(all(r.url.host == "p042" for r in self.requests))

    def test_get_retry_bounded(self):
        calls = []
        def handler(req):
            if "token" in req.url.path:
                return self.handle(req)
            calls.append(req)
            return httpx.Response(503, text="secret")
        self.client.http.close()
        self.client.http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://p042")
        with self.assertRaises(APIError):
            self.client.inventory("cameras")
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.sleeps, [1, 2])

    def test_pagination_cannot_read_another_endpoint(self):
        def handler(req):
            if "token" in req.url.path:
                return self.handle(req)
            return httpx.Response(200, json={"array": [], "_links": {"next": "/api/rest/v1/other"}})
        self.client.http.close()
        self.client.http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://p042")
        with self.assertRaisesRegex(APIError, "unsafe_pagination_link"):
            self.client.inventory("cameras")

    def test_relative_query_pagination(self):
        def handler(req):
            if "token" in req.url.path:
                return self.handle(req)
            if req.url.query:
                return httpx.Response(200, json={"array": [{"id": CAMERA}]})
            return httpx.Response(200, json={"array": [], "_links": {"next": "?page=2"}})
        self.client.http.close()
        self.client.http = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://p042")
        self.assertEqual(self.client.inventory("cameras"), [{"id": CAMERA}])

    def test_invalid_auth_does_not_retry_post(self):
        self.status = 401
        with self.assertRaises(APIError):
            self.client.trigger(trigger().payload(TYPE))
        self.assertEqual(sum(r.url.path.endswith("/events") for r in self.requests), 1)

    def test_timeout_not_retried_or_leaked(self):
        self.post_timeout = True
        with self.assertRaises(APIError) as err:
            self.client.trigger(trigger().payload(TYPE))
        self.assertNotIn("secret", str(err.exception))
        self.assertEqual(sum(r.url.path.endswith("/events") for r in self.requests), 1)

    def test_empty_camera_inventory_blocks_submit(self):
        self.cameras = False
        with self.assertRaisesRegex(APIError, "camera_not_available"):
            self.client.check_mapping(CAMERA, TYPE)

    def test_accepted_response_requires_actual_event_id(self):
        self.post_body = {}
        with self.assertRaisesRegex(APIError, "accepted_without_valid_event_id"):
            self.client.trigger(trigger().payload(TYPE))

    def test_lab_zero_uuid_is_accepted_once_and_never_invented(self):
        self.post_body = {"data": {"id": "00000000-0000-0000-0000-000000000000"}}
        t = trigger()
        with tempfile.TemporaryDirectory() as d:
            ledger = Ledger(Path(d)/"state.db")
            try:
                result = submit(t, self.client, ledger, config(), NOW)
                self.assertEqual(result["status"], "xprotect_accepted")
                self.assertIsNone(result["xprotect_event_id"])
                self.assertFalse(ledger.report()["halted"])
                with self.assertRaisesRegex(Suppressed, "duplicate"):
                    submit(t, self.client, ledger, config(), NOW+timedelta(hours=1))
                self.assertEqual(sum(r.url.path.endswith("/events") for r in self.requests), 1)
            finally:
                ledger.close()

    def test_historical_clip_never_reaches_native_route(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Ledger(Path(d)/"state.db")
            try:
                with self.assertRaises(ValueError):
                    submit(trigger(timestamp_utc=iso(NOW-timedelta(minutes=5))), self.client, ledger, config(), NOW)
                self.assertEqual(self.requests, [])
            finally:
                ledger.close()

    def test_all_scenarios_accept_event_without_claiming_summary(self):
        for label, prompt in PROMPTS.items():
            with tempfile.TemporaryDirectory() as d:
                ledger = Ledger(Path(d)/"state.db")
                try:
                    result = submit(trigger(label=label, prompt=prompt), self.client, ledger, config(label), NOW)
                    self.assertEqual(result["status"], "xprotect_accepted")
                    self.assertEqual(result["hafnia_summary"], "not_yet_verified")
                    self.assertEqual(result["operator_alarm"], "not_yet_verified")
                finally:
                    ledger.close()

    def test_post_rate_limit_halts_future_requests(self):
        self.status = 429
        with tempfile.TemporaryDirectory() as d:
            ledger = Ledger(Path(d)/"state.db")
            try:
                with self.assertRaises(APIError):
                    submit(trigger(), self.client, ledger, config(), NOW)
                self.assertTrue(ledger.report()["halted"])
                with self.assertRaises(Suppressed):
                    submit(trigger(), self.client, ledger, config(), NOW+timedelta(minutes=10))
                self.assertEqual(sum(r.url.path.endswith("/events") for r in self.requests), 1)
            finally:
                ledger.close()

    def test_synthetic_or_unapproved_trigger_never_sends(self):
        for t, c in ((trigger(origin="synthetic"), config()),
                     (trigger(), {**config(), "remote_setup_approved": False}),
                     (trigger(), {**config(), "remote_setup_approved": "false"}),
                     (trigger(), {**config(), "gateway_prompt": "wrong"})):
            with self.assertRaises(ValueError):
                submit(t, self.client, None, c, NOW)
        self.assertEqual(self.requests, [])


class FakeSocket:
    def __init__(self, messages):
        self.messages, self.sent = list(messages), []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def send(self, message):
        self.sent.append(json.loads(message))

    def recv(self, timeout=None):
        if not self.messages:
            raise OSError("synthetic disconnection")
        return json.dumps(self.messages.pop(0))


class StreamTests(unittest.TestCase):
    def event(self, event_id=REMOTE):
        return {"id": event_id, "type": TYPE, "source": f"cameras/{CAMERA}", "time": iso(NOW),
                "data": {"secret": "DO_NOT_LOG"}, "tag": "DO_NOT_LOG"}

    def client(self):
        class Client:
            base_url = "https://p042"
            ssl_context = None
            def token(self):
                return "SYNTHETIC_TOKEN"
        return Client()

    def test_sanitized_output(self):
        self.assertNotIn("DO_NOT_LOG", json.dumps(event_metadata(self.event())))

    def test_scope_and_duplicate_suppression(self):
        watcher = EventWatcher(self.client(), CAMERA, [TYPE])
        outputs = []
        watcher._events({"events": [self.event(), self.event(),
                        {**self.event(), "source": f"cameras/{TYPE}"}]}, outputs.append)
        self.assertEqual(len(outputs), 1)

    def test_reconnect_resume_and_replayed_event_dedup(self):
        first = FakeSocket([{"commandId": 1, "status": 201, "sessionId": SESSION},
                            {"commandId": 2, "status": 200, "subscriptionId": TYPE},
                            {"events": [self.event()]}])
        second = FakeSocket([{"commandId": 3, "status": 200, "sessionId": SESSION},
                             {"events": [self.event(), self.event(str(uuid4()))]}])
        sockets, options = iter([first, second]), []
        def connect(url, **kwargs):
            options.append(kwargs)
            return next(sockets)
        outputs = []
        watcher = EventWatcher(self.client(), CAMERA, [TYPE], connector=connect, sleep=lambda _: None)
        with self.assertRaisesRegex(APIError, "reconnects_exhausted"):
            watcher.watch(outputs.append, reconnects=1)
        self.assertEqual(len(outputs), 2)
        self.assertEqual(second.sent[0]["eventId"], REMOTE)
        self.assertEqual(second.sent[0]["sessionId"], SESSION)
        self.assertEqual(len(second.sent), 1)  # Resumed subscription is retained.
        self.assertEqual(first.sent[1]["filters"][0]["sourceIds"], [CAMERA])
        self.assertIsNone(options[0]["proxy"])

    def test_expired_session_resubscribes(self):
        first = FakeSocket([{"commandId": 1, "status": 201, "sessionId": SESSION},
                            {"commandId": 2, "status": 200}])
        second = FakeSocket([{"commandId": 3, "status": 201, "sessionId": str(uuid4())},
                             {"commandId": 4, "status": 200}])
        sockets = iter([first, second])
        watcher = EventWatcher(self.client(), CAMERA, [TYPE], connector=lambda *a, **k: next(sockets), sleep=lambda _: None)
        with self.assertRaises(APIError):
            watcher.watch(lambda _: None, reconnects=1)
        self.assertEqual(second.sent[1]["command"], "addSubscription")

    def test_subscription_error_does_not_retry_or_leak_body(self):
        sock = FakeSocket([{"commandId": 1, "status": 403, "error": {"errorText": "DO_NOT_LOG"}}])
        watcher = EventWatcher(self.client(), CAMERA, [TYPE], connector=lambda *a, **k: sock)
        with self.assertRaises(APIError) as err:
            watcher.watch(lambda _: None)
        self.assertEqual(err.exception.status, 403)
        self.assertNotIn("DO_NOT_LOG", str(err.exception))
        self.assertEqual(len(sock.sent), 1)

    def test_real_loopback_websocket_handshake_and_observation(self):
        """Uses real sockets only on loopback; server data remains synthetic."""
        commands, headers = [], []
        def handle(ws):
            headers.append(ws.request.headers.get("Authorization"))
            start = json.loads(ws.recv(timeout=2))
            commands.append(start)
            ws.send(json.dumps({"commandId": start["commandId"], "status": 201, "sessionId": SESSION}))
            subscribe = json.loads(ws.recv(timeout=2))
            commands.append(subscribe)
            ws.send(json.dumps({"commandId": subscribe["commandId"], "status": 200}))
            ws.send(json.dumps({"events": [self.event(), self.event()]}))
            try:
                ws.recv(timeout=3)
            except (ConnectionClosed, TimeoutError):
                pass
        outputs = []
        with serve(handle, "127.0.0.1", 0) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.socket.getsockname()[1]
            def connector(url, **kwargs):
                kwargs.pop("ssl")
                return real_connect(f"ws://127.0.0.1:{port}", **kwargs)
            EventWatcher(self.client(), CAMERA, [TYPE], connector=connector).watch(outputs.append, duration=1)
            server.shutdown()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(headers, ["Bearer SYNTHETIC_TOKEN"])
        self.assertEqual([c["command"] for c in commands], ["startSession", "addSubscription"])
        self.assertEqual(len(outputs), 1)


class CLITests(unittest.TestCase):
    def test_logged_out_tailscale_with_null_fields(self):
        class Result:
            returncode = 0
            stdout = '{"BackendState":"NeedsLogin","CurrentTailnet":null,"Peer":null}'
        with patch("adapter.access.subprocess.run", return_value=Result()):
            result = lab_access()
        self.assertFalse(result["reachable"])
        self.assertEqual(result["blocker"], "assigned_peer_not_visible")

    def test_manual_plan_is_local_and_labelled(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, event = Path(d)/"config.json", Path(d)/"event.json"
            cfg.write_text(json.dumps(config()))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["manual", "--camera", CAMERA])
            self.assertEqual(rc, 0)
            event.write_text(out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out), patch("adapter.__main__.client_from") as client:
                rc = main(["--config", str(cfg), "plan", str(event)])
                client.assert_not_called()
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out.getvalue())["mode"], "LOCAL_PLAN_ONLY")

    def test_send_gate_before_any_network_or_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, event = Path(d)/"config.json", Path(d)/"event.json"
            cfg.write_text(json.dumps({**config(), "remote_setup_approved": False}))
            event.write_text(json.dumps(trigger(timestamp_utc=iso(datetime.now(UTC)-timedelta(seconds=30))).record()))
            with contextlib.redirect_stdout(io.StringIO()), patch("adapter.__main__.client_from") as client:
                rc = main(["--config", str(cfg), "send", str(event)])
                client.assert_not_called()
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
