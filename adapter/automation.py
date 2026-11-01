"""Opt-in, bounded initiation from one explicitly selected XProtect camera event.

This is an event bridge, not a detector. Existing native rules are unchanged.
"""
from datetime import datetime

from .ledger import Suppressed
from .model import Trigger, UTC, guid
from .service import submit
from .stream import event_metadata


class RunComplete(Exception):
    """The operator-selected send limit has been reached."""


class EventInitiator:
    def __init__(self, client, ledger, config, input_type, *, armed=False,
                 max_sends=1, clock=lambda: datetime.now(UTC)):
        self.client, self.ledger, self.config = client, ledger, config
        self.camera = guid(config["camera_id"])
        self.input_type = guid(input_type)
        outputs = {guid(config["trigger_event_type_id"])}
        outputs.update(guid(t) for t in config["watch_event_type_ids"])
        if self.input_type in outputs:
            raise ValueError("Request/result events cannot feed analysis")
        if type(max_sends) is not int or not 1 <= max_sends <= 3:
            raise ValueError("An automatic run allows 1..3 sends")
        if armed and (config.get("remote_setup_approved") is not True or
                      config.get("gateway_contract_verified") is not True):
            raise ValueError("Native setup approval and verification required")
        self.armed, self.max_sends, self.clock = armed, max_sends, clock
        self.sent = 0

    def accept(self, message):
        if "id" not in message:
            return message  # Preserve observer-gap notices; never turn them into triggers.
        event = event_metadata(message)
        if event["source"] != "cameras/" + self.camera or event["type"] != self.input_type:
            return {"status": "ignored", "reason": "outside_selected_input"}
        trigger = Trigger(event["id"], self.camera, event["time"], "xprotect_event",
                          label=self.config["scenario"], prompt=self.config["gateway_prompt"])
        now = self.clock()
        try:
            trigger.validate_live_request(now)
        except ValueError:
            return {"status": "ignored", "reason": "event_not_fresh"}
        if not self.armed:
            return {"status": "dry_run", "trigger_id": trigger.event_id,
                    "origin": trigger.origin, "note": "No request sent"}
        if self.sent >= self.max_sends:
            raise RunComplete
        try:
            result = submit(trigger, self.client, self.ledger, self.config, now)
        except Suppressed as exc:
            return {"status": "suppressed", "reason": str(exc)}
        self.sent += 1
        return result
