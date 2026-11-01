# iCit Incident Review: XProtect + Hafnia

A manual trigger requests Hafnia analysis of a 30-second XProtect recording.
The native gateway stores an AI-labelled bookmark and raises a camera review
alarm when the answer contains the scenario's positive token.

Gate and sidewalk completed this flow in the organizer lab. Railway transport
worked, but both tested answers incorrectly reported clear tracks. These few
clips are a demonstration, not an accuracy benchmark. Operators must review
footage before acting; a missing alarm does not establish scene safety.

## What this repository contains

Only the new standalone manual-trigger connector, synthetic configuration/test
fixtures, native TEST setup script and essential reproduction/results documents.
There is no proprietary VLM source, binary, model, private-plugin interface,
real account configuration, credential, raw log or detailed live-data export.
Prompts and organizer scenario names are needed to reproduce the demonstration.
The demonstration video contains organizer camera imagery and visible Smart
Client metadata; it is published separately from the source.

```text
Manual trigger -> duplicate / cooldown / budget checks
  -> scoped XProtect user event -> native rule and Hafnia webhook
  -> actual Hafnia answer -> bookmark + positive-token review alarm
```

## Install and check

Python 3.12:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m adapter --help
.venv/bin/python -m adapter doctor
```

The public package has 41 tests. Automatic detection and private inference are
not part of this demonstration.

Follow [REPRODUCE.md](submission/REPRODUCE.md) for the reviewed p042 setup.
Copy a config/*.example.json into .local/lab.json and replace synthetic IDs
with your authorized lab inventory. Approve and verify the native setup before
setting its two approval booleans. The connector is restricted to assigned p042.

Credentials are prompted securely or supplied through XPROTECT_USERNAME and
XPROTECT_PASSWORD; XPROTECT_CA_FILE selects a private CA. No .env file is loaded.
Use the scoped basic user, not Administrator. HTTPS verifies certificates.
The organizer lab's explicit allow_tailnet_http option requires the matching
online Tailscale peer. Keep company access separate from the organizer network.

## Run one reviewed request

Start observation in one terminal, then create and send a fresh trigger in another:

```bash
.venv/bin/python -m adapter watch --seconds 120
# Other terminal; replace CAMERA_UUID with the actual configured gate camera:
.venv/bin/python -m adapter manual --camera CAMERA_UUID --scenario school_gate_break_in_night > .local/trigger.json
.venv/bin/python -m adapter send .local/trigger.json
.venv/bin/python -m adapter send .local/trigger.json
.venv/bin/python -m adapter status
```

The first send reports acceptance; the repeat is suppressed. Acceptance alone
is not a completed summary. Inspect native history, the bookmark and alarm.
All scenarios share one durable ledger: ten attempted sends per UTC day and a
120-second camera cooldown. Unknown POST outcomes halt sending without retries;
inspect event/gateway history before resume --reviewed-history. Do not remove
the ledger to bypass safeguards.

The installed native route assigns server receipt time, selects a fixed camera,
and analyzes 20 seconds before / 10 seconds after receipt. Requests older than
30 seconds are rejected. Historical replay is unsupported. REST acceptance can
contain a zero UUID; actual event IDs are observed over WebSocket.

## Results and access

- [Results, validation and limitations](submission/RESULTS.md)
- [Reproduction and rollback](submission/REPRODUCE.md)
- [Authorized judge access to the running lab](submission/JUDGE_ACCESS.md)
- [Third-party dependency notices](submission/THIRD_PARTY_NOTICES.txt)

MANIFEST.json lists the exact published source files and hashes. The public
source does not contain the private CEO review pack or submission contact details.
