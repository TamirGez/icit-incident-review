# Installation and configuration

The gate and sidewalk workflows have produced authentic Hafnia summaries,
bookmarks and Smart Client alarms on the assigned p042 lab.
See the [test record](RESULTS.md) for the evaluated scenarios and scope.
The recorded demonstration uses manual requests. The [workflow guide](WORKFLOW.md)
covers the operator queue and optional camera-event intake.

## 1. Environment and access

Observed: XProtect Corporate 2026 R1, Management Client 26.1.19310.1,
Smart Client 26.1.10902.6, Hafnia gateway 2.0.150.52593 and
MilestonePSTools 25.2.61. Connector: Python 3.12.3 and requirements.lock.

Reach only the assigned p042 machine on the organizer Tailscale network.
Use RDP for Windows administration. Inside p042, verify hostname and the
Milestone XProtect Management Server service before running setup commands.
Hafnia API requests execute inside p042, against localhost:15443.

Read the installed C:\HackathonKit instructions. Do not change Tailscale,
firewall, administrator passwords, gateway connection settings or product
versions. Do not reset, shut down or restart the organizer machine.

## 2. Native TEST configuration

Review the named ICIT_TEST_* objects before running the setup script with
`-ApprovedTestSetup`. This procedure is scoped to those objects.

In Management Client, Tools > Options > Analytics Events, enable the existing
port 9090, following the installed organizer guide. Under Rules and Events >
Analytics Events, create and save:

- ICIT_TEST_RAIL_REVIEW
- ICIT_TEST_GATE_REVIEW
- ICIT_TEST_SIDEWALK_REVIEW

Copy the connector setup files to p042. From the package root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_native.ps1 -ApprovedTestSetup
```

The script uses the current Windows identity for MilestonePSTools. It requests
the gateway password securely, keeps the gateway session in memory and logs out.
It never puts passwords or tokens in command arguments, output or files.
TLS certificate relaxation is limited to curl against the installed loopback
Hafnia gateway. The Linux XProtect client has no TLS-verification bypass.

The script resolves camera IDs by name, creates/checks three saved prompts,
request events, fixed-camera webhooks, native rules and gateway keyword rules.
It creates a scoped basic user only if missing and asks securely for its password.
Existing objects with incompatible settings stop the setup instead of being
silently overwritten. A non-secret setup report is written to the Windows
TEMP folder; ReportPath can select another local output file.

| Prefix | Camera | Positive review token |
|---|---|---|
| RAIL | person_on_railway_tracks | RAIL_INTRUSION |
| GATE | school_gate_break_in_night | GATE_INTERACTION |
| SIDEWALK | escooter_left_across_sidewalk | SIDEWALK_BLOCKED |

For each prefix, ICIT_TEST_*_REQUEST invokes only ICIT_TEST_*_SUMMARY through
ICIT_TEST_*_TO_HAFNIA. The webhook selects its specific camera, model
traffic-general, Create Bookmark Yes, PreBuffer 20 and PostBuffer 10.
Its exact parameter names were checked in the installed Smart Client generator.
Gateway ICIT_TEST_*_REVIEW matches the positive token and raises the matching
analytics event. Keep result events out of analysis input rules to prevent loops.

Complete role permissions and alarm definitions in Management Client:

1. Security > Roles > ICIT_TEST_CONNECTOR > External Events: grant Read and
   Trigger separately on the three ICIT_TEST_*_REQUEST events. Leave Edit,
   Delete and predefined events ungranted. The script grants camera read,
   live/playback and bookmark read only on the three selected cameras; it grants
   analytics-event and alarm read without administration privileges.
2. Alarms > Alarm Definitions: create ICIT_TEST_*_OPERATOR_REVIEW for each
   Analytics Events > ICIT_TEST_*_REVIEW, selecting only its matching camera.
   Enable it with the Always time profile. Instructions should require the
   operator to inspect the clip and AI-generated bookmark before acting.
3. Save changes and verify all three native input rules are active. Do not edit
   default recording rules. New event definitions may require Smart Client
   logout/login to appear in its manual event list.

The included native-rule template defines the event-to-webhook mapping.
The procedure was verified against the installed p042 configuration.

## 3. Connector configuration and live test

Install and test locally:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m adapter doctor
```

Copy the matching config/*.example.json to .local/lab.json. Replace synthetic
IDs using the setup report and inventory. Use the analytics event ID as the
camera watch type and the user-defined event ID as trigger_event_type_id.
For this organizer lab, base_url is http://p042 and allow_tailnet_http is true;
the connector verifies the assigned online Tailscale peer and DNS first.
Use the scoped basic user through interactive input or XPROTECT_USERNAME and
XPROTECT_PASSWORD. Do not use Administrator for the connector.

After reviewing the native setup, set remote_setup_approved and
gateway_contract_verified true. Keep event_time_basis set to server_receipt.
Start the watcher before sending:

```bash
.venv/bin/python -m adapter inventory cameras
.venv/bin/python -m adapter inventory userDefinedEvents
.venv/bin/python -m adapter watch --seconds 120
# In another terminal; replace CAMERA_UUID with the gate camera ID:
.venv/bin/python -m adapter manual --camera CAMERA_UUID --scenario school_gate_break_in_night > .local/trigger.json
.venv/bin/python -m adapter send .local/trigger.json
.venv/bin/python -m adapter send .local/trigger.json
.venv/bin/python -m adapter status
```

Create and send within 30 seconds. The first POST should report
xprotect_accepted; the second should report suppressed/duplicate, with no new
POST. All configurations must share one ledger for the ten-attempt UTC daily
cap and 120-second per-camera cooldown. Manual Smart Client/API summaries are
outside that ledger; inspect actual gateway quota separately.

Important installed behavior: user-defined events receive server receipt time,
ignoring a historical time supplied in the REST body. The connector rejects
requests outside the 30-second freshness window.
The gateway waits for the post-buffer and analyzes the actual event-time window.
Read exact clip bounds from gateway history and the bookmark.

The installed REST response uses a zero UUID for accepted user events. The
connector reports a null REST event ID; the real ID arrives over WebSocket.
User-defined events are never retained for GET /events. Analytics events may
be read according to their retention policy. An HTTP acceptance alone does not
prove a completed summary or a visible alarm.

## 4. Verify the full trace

In Smart Client > Summarization > History, select the new Webhook request.
Confirm the matching ICIT_TEST_*_SUMMARY trigger name, camera, actual UTC window,
Completed status and unmodified Hafnia text. Then inspect Alarm Manager for the
matching camera/review event. The bookmark contains the full answer prefixed
“This summary is AI-generated”. Analytics events contain the matched keyword,
not the complete answer.

Preserve the local trigger ID, REST acceptance, observed request and analytics
UUIDs, summary ID, clip URI, bookmark/alarm references and quota. Do not infer
causation from timestamp proximity alone: also verify the single matching input
rule, prompt, fixed camera, positive keyword and output alarm definition.

A clear/uncertain response does not match the positive-token rule, so it produces
no alarm. Operators should base decisions on the recording. The [test record](RESULTS.md)
documents the observed scenario outcomes.

## 5. Reliability and rollback

The suite covers malformed/expired/future timestamps, fresh native requests,
zero-UUID receipts, missing cameras, invalid authentication, 429 and transport
failures, no POST retries, duplicate persistence, shared budgets, crash review,
scoped subscriptions and reconnect/resume behavior. Live evidence covers the
actual REST/WebSocket transport, native summary/bookmark/alarm flow and duplicate
suppression. Live disconnect, recording outages, quota exhaustion and restart
were not deliberately induced.

After an uncertain POST outcome, inspect gateway/event history before using
resume --reviewed-history. Existing trigger IDs remain consumed. Do not delete
the ledger to bypass safeguards.

For rollback, first disable the three ICIT_TEST_*_TO_HAFNIA rules. Remove only
the new TEST rules, gateway keyword rules, webhook registrations, prompts,
alarm/analytics/request definitions and scoped account/role after reviewing the
recorded IDs. Preserve default rules, recording settings and unrelated objects.
Do not change the organizer's credentials or network settings.
