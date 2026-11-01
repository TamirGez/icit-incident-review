# Gate review: automatic event intake and human follow-up

The intended operator is a campus duty operator reviewing a school-gate alert.
Review visible padlock/gate activity, check authorized maintenance with the duty
caretaker, then record follow-up. A model phrase about intent is not a finding of
unauthorized entry. The public page includes an interactive **browser replay**;
it does not control XProtect, send a message, or contain a live detector.

## Bounded automatic initiation

The new bridge consumes an existing XProtect camera event using the scoped
WebSocket observer. It uses the event UUID as the durable trigger ID and records
`origin=xprotect_event`. It requests the **same existing native TEST workflow**;
there is no private plugin, inference engine or new remote configuration.

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

This bridge is **implemented and tested synthetically**. All filmed native
requests used manual triggers. Read-only live gate motion checks received no
input events; no automatic Hafnia request was sent. An event type appearing in
inventory does not prove that a camera emits it or that the account receives it.
Automatic end-to-end behavior remains unverified until a fresh input event,
request, completed summary, bookmark and alarm are all traced. Camera settings
and default recording rules were not changed to manufacture that result.

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
answer can produce no alarm and thus no review case. The known railway failure
remains visible in results. Do not infer safety from an empty queue. This is a
bounded command-line observer; it is not installed as an unattended service.

The browser replay uses an illustrative case and fixed outcome choices. It saves
only local browser state, ignores repeated events, keeps uncertain cases open,
and still operates if storage is denied. Native queue and browser replay are
separate; the public page has no access to private lab data.
