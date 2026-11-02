# iCit Incident Review

**XProtect video. Hafnia context. Operator follow-up.**

Incident Review connects a 30-second XProtect recording to a Hafnia summary,
an AI-labelled video bookmark and an operator review alarm. A campus duty operator
can inspect gate activity, confirm authorized maintenance and record the next action.

[Watch the demo and try the review workflow](https://tamirgez.github.io/icit-incident-review/)
· [View the p042 lab](submission/JUDGE_ACCESS.md)

## How it works

```text
Manual request -> duplicate, cooldown and request-budget checks
  -> XProtect event -> native rule and Hafnia webhook
  -> AI-labelled bookmark + matching review alarm
  -> operator review and follow-up
```

The demonstrated gate workflow produced three summaries, three bookmarks and
three alarms. A sidewalk-obstruction request completed the same native flow.
Median completion time for the three gate requests was **15.070 seconds**,
including the post-buffer wait. [Results and measurement method](submission/RESULTS.md).

## Install

Requires Python 3.12 and access to the organizer's p042 XProtect environment.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m adapter doctor
```

The test suite contains **53 automated checks** covering the connector, event
intake and operator review queue.

## Configure

Follow [Installation and configuration](submission/REPRODUCE.md) to configure
the native XProtect events, Hafnia webhook and review alarms. Then create a local
configuration from the gate example:

```bash
mkdir -p .local
cp config/school_gate_break_in_night.example.json .local/lab.json
```

Replace the example IDs with the camera and event IDs from the authorized lab.
Set `remote_setup_approved` and `gateway_contract_verified` only after checking
the native configuration. The connector is restricted to p042.

Use the scoped XProtect basic account. Credentials are prompted interactively
or supplied through `XPROTECT_USERNAME` and `XPROTECT_PASSWORD`.
`XPROTECT_CA_FILE` selects a CA certificate. HTTPS verifies certificates; the
lab's `allow_tailnet_http` option requires a verified online Tailscale peer.

## Run a gate review

Start the observer, then create and send a fresh request in a second terminal:

```bash
.venv/bin/python -m adapter watch --seconds 120
# Second terminal: replace CAMERA_UUID with the configured gate camera ID.
.venv/bin/python -m adapter manual --camera CAMERA_UUID --scenario school_gate_break_in_night > .local/trigger.json
.venv/bin/python -m adapter send .local/trigger.json
.venv/bin/python -m adapter send .local/trigger.json
.venv/bin/python -m adapter status
```

The first send reports acceptance; the repeat is suppressed. Inspect the
completed summary, bookmark and matching alarm in Smart Client. Requests must
be sent within 30 seconds because the native rule uses server receipt time.

All scenarios share one durable ledger, a ten-attempt UTC daily cap and a
120-second camera cooldown. An uncertain POST outcome pauses sending until
history has been reviewed. Recovery and rollback are covered in the setup guide.

## Documentation

- [Installation, verification and rollback](submission/REPRODUCE.md)
- [Operator queue and optional event intake](submission/WORKFLOW.md)
- [Results and validation scope](submission/RESULTS.md)
- [Measurement method and per-run data](submission/MEASUREMENTS.md)
- [Judge access](submission/JUDGE_ACCESS.md)
- [Third-party notices](submission/THIRD_PARTY_NOTICES.txt)
