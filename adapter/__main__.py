import argparse
import getpass
import json
import os
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from .access import lab_access
from .ledger import Ledger, Suppressed
from .model import Trigger, UTC, PROMPTS, guid, iso
from .service import submit
from .stream import EventWatcher, event_metadata
from .xprotect import XProtect, APIError
from .automation import EventInitiator, RunComplete
from .review import ReviewQueue


def emit(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def load_json(path):
    if Path(path).stat().st_size > 1_048_576:
        raise ValueError("JSON input is larger than 1 MB")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def client_from(config):
    access = lab_access()
    if not access["reachable"]:
        raise APIError(access["blocker"])
    username = os.environ.get("XPROTECT_USERNAME") or input("Scoped XProtect basic username: ")
    password = os.environ.get("XPROTECT_PASSWORD") or getpass.getpass("Scoped XProtect password: ")
    return XProtect(config["base_url"], username, password,
                    ca_file=os.environ.get("XPROTECT_CA_FILE"),
                    allow_tailnet_http=config.get("allow_tailnet_http", False))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local XProtect / Hafnia hackathon connector")
    parser.add_argument("--config", default=".local/lab.json")
    parser.add_argument("--ledger", default=".local/attempts.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Read-only Tailscale and assigned-host check")
    inv = sub.add_parser("inventory", help="Read-only camera or event-type inventory")
    inv.add_argument("resource", choices=["cameras", "eventTypes", "userDefinedEvents"])
    create = sub.add_parser("manual", help="Create a manual trigger JSON; sends nothing")
    create.add_argument("--camera", required=True)
    create.add_argument("--scenario", choices=list(PROMPTS), default="person_on_railway_tracks")
    create.add_argument("--timestamp", help="ISO timestamp with timezone; default now. Sending requires age <=30 seconds")
    plan = sub.add_parser("plan", help="Validate a trigger and print its proposed event; sends nothing")
    plan.add_argument("trigger_file")
    send = sub.add_parser("send", help="Submit one trigger after approved native gateway setup")
    send.add_argument("trigger_file")
    watch = sub.add_parser("watch", help="Read-only, bounded event subscription")
    watch.add_argument("--seconds", type=int, default=120)
    watch.add_argument("--review-db", help="Create local operator cases from scoped camera review events")
    auto = sub.add_parser("automate", help="Bounded camera-event initiation; dry run unless --armed")
    auto.add_argument("--input-event-type", required=True)
    auto.add_argument("--seconds", type=int, default=120)
    auto.add_argument("--max-sends", type=int, default=1)
    auto.add_argument("--armed", action="store_true")
    review = sub.add_parser("review", help="Local operator queue; never changes XProtect")
    review.add_argument("action", choices=["list", "acknowledge", "follow_up", "close"])
    review.add_argument("--db", default=".local/review.sqlite3")
    review.add_argument("--case")
    review.add_argument("--note", default="")
    review.add_argument("--footage-reviewed", action="store_true")
    event = sub.add_parser("event", help="Read one XProtect event as sanitized metadata")
    event.add_argument("event_id")
    sub.add_parser("status", help="Local reservations, outcomes and halt state")
    resume = sub.add_parser("resume", help="Clear POST-error halt after checking gateway and event history")
    resume.add_argument("--reviewed-history", action="store_true", required=True)
    args = parser.parse_args(argv)
    client, ledger, queue = None, None, None
    try:
        if args.command == "doctor":
            access = lab_access()
            emit(access)
            return 0 if access["reachable"] else 2
        if args.command == "manual":
            t = args.timestamp or iso(datetime.now(UTC))
            emit(Trigger(str(uuid4()), args.camera, t, "manual", label=args.scenario,
                         prompt=PROMPTS[args.scenario]).record())
            return 0
        if args.command == "review":
            queue = ReviewQueue(args.db)
            emit(queue.report() if args.action == "list" else queue.transition(
                args.case, args.action, args.note, footage_reviewed=args.footage_reviewed))
            return 0
        if args.command in ("status", "resume"):
            ledger = Ledger(args.ledger)
            if args.command == "resume":
                ledger.resume()
            emit(ledger.report())
            return 0
        config = load_json(args.config)
        if args.command == "automate":
            if not 1 <= args.seconds <= 600:
                raise ValueError("Watch duration is 1..600 seconds")
            # Validate input isolation and arming before credentials or network access.
            initiator = EventInitiator(None, None, config, args.input_event_type,
                                      armed=args.armed, max_sends=args.max_sends)
        if args.command in ("send", "plan"):
            trigger = Trigger(**load_json(args.trigger_file))
            if args.command == "plan":
                trigger.validate_live_request(datetime.now(UTC))
                now = datetime.now(UTC)
                start, end = now-timedelta(seconds=trigger.before_seconds), now+timedelta(seconds=trigger.after_seconds)
                emit({"mode": "LOCAL_PLAN_ONLY", "payload": trigger.payload(config["trigger_event_type_id"]),
                      "estimated_clip_start_utc": iso(start), "estimated_clip_end_utc": iso(end), "prompt": trigger.prompt,
                      "note": "Native user events use server receipt time; these bounds are estimates. Gateway waits for post-buffer; verify actual bounds in history"})
                return 0
            # Enforce setup gates before any credential prompt or network request.
            if config.get("remote_setup_approved") is not True or config.get("gateway_contract_verified") is not True:
                raise ValueError("Approve and verify the native lab setup before sending")
        client = client_from(config)
        if args.command == "inventory":
            rows = client.inventory(args.resource)
            emit({"resource": args.resource, "items": [{
                k: r.get(k) for k in ("id", "name", "displayName", "generatorType", "generatorSubtype") if k in r}
                for r in rows]})
        elif args.command == "event":
            emit(event_metadata(client.event(args.event_id)))
        elif args.command == "watch":
            if args.review_db:
                queue = ReviewQueue(args.review_db)
            EventWatcher(client, config["camera_id"], config["watch_event_type_ids"],
                         user_event_ids=[config["trigger_event_type_id"]]).watch(
                (lambda e: emit(queue.ingest(e, config))) if queue else emit, duration=args.seconds)
        elif args.command == "automate":
            ledger = Ledger(args.ledger) if args.armed else None
            initiator.client, initiator.ledger = client, ledger
            def receive(e):
                emit(initiator.accept(e))
                if initiator.sent >= initiator.max_sends:
                    raise RunComplete
            try:
                EventWatcher(client, config["camera_id"], [args.input_event_type]).watch(
                    receive, duration=args.seconds)
            except RunComplete:
                pass
            emit({"status": "automatic_run_finished", "sent": initiator.sent,
                  "mode": "armed" if args.armed else "dry_run"})
        elif args.command == "send":
            config["camera_id"] = guid(config["camera_id"])
            config["trigger_event_type_id"] = guid(config["trigger_event_type_id"])
            ledger = Ledger(args.ledger)
            emit(submit(trigger, client, ledger, config, datetime.now(UTC)))
        return 0
    except Suppressed as exc:
        emit({"status": "suppressed", "reason": str(exc)})
        return 3
    except APIError as exc:
        error = {"status": "blocked", "code": exc.code, "http_status": exc.status}
        if exc.receipt is not None:
            error["receipt"] = exc.receipt
        emit(error)
        return 2
    except (ValueError, KeyError, TypeError, OSError, EOFError, sqlite3.Error) as exc:
        # Do not print raw input, file paths or server bodies, which can contain secrets.
        emit({"status": "invalid_input_or_configuration", "error_type": type(exc).__name__})
        return 2
    except KeyboardInterrupt:
        return 130
    finally:
        if client:
            client.close()
        if ledger:
            ledger.close()
        if queue:
            queue.close()


if __name__ == "__main__":
    sys.exit(main())
