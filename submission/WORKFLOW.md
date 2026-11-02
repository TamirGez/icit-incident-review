# Operator review and event intake

A campus duty operator reviews the school-gate alert and its recorded context.
Review visible padlock/gate activity, check authorized maintenance with the duty
caretaker, then record follow-up. A model phrase about intent is not a finding of
unauthorized entry. The [interactive demo](https://tamirgez.github.io/icit-incident-review/) uses a
browser replay with illustrative review outcomes.

## Bounded automatic initiation

The event bridge consumes an existing XProtect camera event using the scoped
WebSocket observer. It uses the event UUID as the durable trigger ID and records
`origin=xprotect_event`. It invokes the configured native XProtect rule and Hafnia webhook.

Resolve an appropriate event type with `inventory eventTypes`, inspect the
selected camera's actual event feed, and use a read-only dry run first:

```bash
python -m adapter --config .local/gate.json automate --input-event-type INPUT_EVENT_UUID --seconds 120
# Only after approving the selected input and checking actual gateway quota:
python -m adapter --config .local/gate.json automate --input-event-type INPUT_EVENT_UUID --seconds 120 --max-sends 1 --armed
```

Default is dry run, with zero sends and zero reservations. Each armed run sends
at most one request by default (explicit maximum three), then exits; runtime is
bounded to 600 seconds. Existing duplicates, 120-second camera cooldown, shared
UTC daily cap and uncertain-POST halt apply. Stale events are ignored. The native
request event and configured result types cannot be inputs, preventing feedback.
Use one ledger for manual and automatic runs. Never delete it to bypass limits.
Manual gateway requests are outside this ledger; check gateway quota separately.

Validation scope: the event bridge has synthetic guardrail coverage. The filmed
native requests used manual triggers. Two 120-second live gate observations
received no input events, so the automatic trigger path is not live-validated.
Use the dry run to verify the selected camera emits an appropriate event before
arming, then trace request, completed summary, bookmark and alarm.

## Local operator case queue

```bash
python -m adapter --config .local/gate.json watch --seconds 120 --review-db .local/review.sqlite3
python -m adapter review list
python -m adapter review acknowledge --case EVENT_UUID
python -m adapter review follow_up --case EVENT_UUID --note "Duty caretaker to verify authorized maintenance"
python -m adapter review close --case EVENT_UUID --footage-reviewed --note "Reviewed footage; caretaker confirmed the gate is secured"
```

Matching native camera review events automatically create cases, once per event
UUID across restarts. Request events and other cameras are rejected. Gate and
railway cases receive priority 1; sidewalk cases priority 2. This is a simple
operator policy, not a model confidence or urgency estimate. Active cases sort
before closed cases, then by priority and receipt time. Acknowledge precedes
follow-up/closure; follow-up and closure require a note, and closure also requires
explicit footage review. SQLite retains an action history locally with restricted
file permissions. No XProtect alarm state or external message is changed.

A positive-token event queue inherits the model's blind spots: an incorrect clear
answer can produce no alarm and thus no review case. The [test record](RESULTS.md) contains the observed scenario outcomes. Do not infer safety from an empty queue. This is a
bounded command-line observer; it is not installed as an unattended service.

The browser replay uses an illustrative case and fixed outcome choices. It saves
only local browser state, ignores repeated events, keeps uncertain cases open,
and still operates if storage is denied. Native queue and browser replay are
separate; the browser example stores its state locally.
