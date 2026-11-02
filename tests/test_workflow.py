"""Event intake and operator workflow tests using synthetic fixtures."""
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from adapter.automation import EventInitiator, RunComplete
from adapter.ledger import Ledger
from adapter.model import iso
from adapter.review import ReviewQueue
from adapter.xprotect import APIError
from test_connector import CAMERA, TYPE, REMOTE, NOW, config

INPUT = "55555555-5555-4555-8555-555555555555"


class FakeClient:
    def __init__(self):
        self.posts = []
        self.error = None

    def check_mapping(self, camera, event_type):
        assert camera == CAMERA and event_type == TYPE

    def trigger(self, body):
        self.posts.append(body)
        if self.error:
            raise self.error
        return None


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.ledger = Ledger(self.path / "attempts.sqlite3")
        self.addCleanup(self.ledger.close)
        self.queue = ReviewQueue(self.path / "review.sqlite3")
        self.addCleanup(self.queue.close)
        self.config = config("school_gate_break_in_night")
        self.config["watch_event_type_ids"] = [REMOTE]
        self.client = FakeClient()

    def event(self, **changes):
        return {"id": str(uuid4()), "source": "cameras/" + CAMERA,
                "type": INPUT, "time": iso(NOW), **changes}

    def initiator(self, **kwargs):
        return EventInitiator(self.client, self.ledger, self.config, INPUT,
                              clock=lambda: NOW, **kwargs)

    def test_dry_run_never_posts_or_reserves(self):
        result = self.initiator().accept(self.event())
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(self.client.posts, [])
        self.assertEqual(self.ledger.report()["attempts"], [])

    def test_rejects_feedback_input_types(self):
        for input_type in (TYPE, REMOTE):
            with self.assertRaises(ValueError):
                EventInitiator(self.client, self.ledger, self.config, input_type)

    def test_arming_requires_verified_native_setup(self):
        self.config["gateway_contract_verified"] = False
        with self.assertRaises(ValueError):
            self.initiator(armed=True)

    def test_outside_camera_and_stale_events_do_not_send(self):
        bridge = self.initiator(armed=True)
        for event in (self.event(source="cameras/" + REMOTE),
                      self.event(type=REMOTE), self.event(time=iso(NOW-timedelta(seconds=31))),
                      self.event(time=iso(NOW+timedelta(seconds=3)))):
            self.assertEqual(bridge.accept(event)["status"], "ignored")
        self.assertEqual(self.client.posts, [])

    def test_auto_origin_and_one_send_limit(self):
        bridge = self.initiator(armed=True)
        result = bridge.accept(self.event())
        self.assertEqual(result["origin"], "xprotect_event")
        self.assertIn("xprotect_event", self.client.posts[0]["tag"])
        with self.assertRaises(RunComplete):
            bridge.accept(self.event())
        self.assertEqual(len(self.client.posts), 1)

    def test_restart_duplicate_and_shared_cooldown(self):
        event = self.event()
        self.initiator(armed=True).accept(event)
        second = self.initiator(armed=True)
        self.assertEqual(second.accept(event)["reason"], "duplicate")
        self.assertIn("cooldown", second.accept(self.event())["reason"])
        self.assertEqual(len(self.client.posts), 1)

    def test_ambiguous_auto_post_halts_without_retry(self):
        self.client.error = APIError("transport_uncertain")
        with self.assertRaises(APIError):
            self.initiator(armed=True).accept(self.event())
        self.assertTrue(self.ledger.report()["halted"])
        self.assertEqual(self.initiator(armed=True).accept(self.event())["status"], "suppressed")
        self.assertEqual(len(self.client.posts), 1)

    def test_gap_notice_is_preserved_without_post(self):
        gap = {"status": "new_session_after_disconnect", "provenance": "observer_gap_possible"}
        self.assertEqual(self.initiator(armed=True).accept(gap), gap)
        self.assertEqual(self.client.posts, [])

    def test_queue_only_accepts_scoped_camera_results(self):
        for event in (self.event(), self.event(type=REMOTE, source="cameras/" + TYPE),
                      self.event(type=TYPE, source="userDefinedEvents/" + TYPE)):
            self.assertEqual(self.queue.ingest(event, self.config)["status"], "ignored")
        self.assertEqual(self.queue.report()["cases"], [])

    def test_queue_deduplicates_across_reopen(self):
        event = self.event(type=REMOTE)
        self.assertEqual(self.queue.ingest(event, self.config)["status"], "case_created")
        other = ReviewQueue(self.path / "review.sqlite3")
        try:
            self.assertEqual(other.ingest(event, self.config)["status"], "duplicate")
            self.assertEqual(len(other.report()["audit"]), 1)
        finally:
            other.close()

    def test_followup_requires_review_and_note(self):
        event = self.event(type=REMOTE)
        self.queue.ingest(event, self.config)
        with self.assertRaises(ValueError):
            self.queue.transition(event["id"], "close", "done", footage_reviewed=True)
        self.queue.transition(event["id"], "acknowledge")
        with self.assertRaises(ValueError):
            self.queue.transition(event["id"], "follow_up")
        self.queue.transition(event["id"], "follow_up", "Check authorized maintenance with duty caretaker")
        with self.assertRaises(ValueError):
            self.queue.transition(event["id"], "close", "Caretaker confirmed gate secured")
        self.queue.transition(event["id"], "close", "Caretaker confirmed gate secured", footage_reviewed=True)
        self.assertEqual(self.queue.report()["cases"][0]["status"], "closed")
        self.assertEqual(len(self.queue.report()["audit"]), 4)

    def test_queue_prioritizes_gate_over_sidewalk(self):
        sidewalk = dict(self.config, scenario="blocked_sidewalk")
        self.queue.ingest(self.event(type=REMOTE), sidewalk)
        gate = self.event(type=REMOTE)
        self.queue.ingest(gate, self.config)
        self.assertEqual(self.queue.report()["cases"][0]["id"], gate["id"])
