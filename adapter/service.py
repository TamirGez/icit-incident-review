from .model import PROMPTS
from .xprotect import APIError


def submit(trigger, client, ledger, config, now):
    if trigger.origin == "synthetic":
        raise ValueError("Synthetic triggers cannot be sent to the lab")
    if config.get("remote_setup_approved") is not True or config.get("gateway_contract_verified") is not True:
        raise ValueError("Owner-approved remote setup and installed gateway verification are required")
    if trigger.camera_id != config["camera_id"]:
        raise ValueError("Trigger is outside the configured camera")
    if config.get("scenario") != trigger.label or config.get("gateway_prompt") != PROMPTS[trigger.label] or (
            config.get("before_seconds"), config.get("after_seconds")) != (
                trigger.before_seconds, trigger.after_seconds):
        raise ValueError("Trigger must match the verified gateway prompt and clip window")
    ledger.check_ready(trigger.event_id)
    if config.get("event_time_basis") != "server_receipt":
        raise ValueError("Verify server_receipt timing for the installed native user-event route")
    trigger.validate_live_request(now)
    event_type = config["trigger_event_type_id"]
    client.check_mapping(trigger.camera_id, event_type)
    ledger.reserve(trigger, now, daily_cap=config.get("daily_test_cap", 10),
                   cooldown=config.get("cooldown_seconds", 120))
    try:
        remote_id = client.trigger(trigger.payload(event_type))
    except APIError as exc:
        # All POST errors require review, including 429, invalid auth and
        # ambiguous timeouts. Never resubmit automatically or free the slot.
        ledger.finish(trigger.event_id, "needs_review", detail=exc.code, halt=True)
        raise
    ledger.finish(trigger.event_id, "xprotect_accepted", remote_id=remote_id)
    return {"trigger_id": trigger.event_id, "xprotect_event_id": remote_id,
            "status": "xprotect_accepted", "origin": trigger.origin,
            "event_id_source": "REST" if remote_id else "not_returned; observe WebSocket",
            "clip_time_basis": "server_receipt; inspect gateway history for actual bounds",
            "hafnia_summary": "not_yet_verified", "operator_alarm": "not_yet_verified"}
