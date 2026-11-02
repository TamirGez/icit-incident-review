# Test record — XProtect + Hafnia Incident Review

## Demonstrated workflows

| Workflow | Observed native outputs |
|---|---|
| School gate review | Three completed summaries, three AI-labelled bookmarks and three operator review alarms |
| Sidewalk obstruction | One completed summary, one AI-labelled bookmark and one matching review alarm |

The filmed native requests were initiated manually in the organizer's p042 lab.
Final repeat requests were suppressed without another event POST. The video uses
authentic Smart Client playback with labelled cuts. The interactive operator
panel is a browser replay; its actions are local to that browser.

The gate requests completed in 14.637, 15.070 and 15.773 seconds, measured from
gateway creation to its final Completed update, including the post-buffer wait.
[Measurement method and full per-run table](MEASUREMENTS.md).

## Software verification

The **53-test suite passed on Python 3.12 / Ubuntu 24.04**. Coverage includes
scoped authentication, timestamp validation, REST response handling, pagination,
durable duplicates, cooldown/shared budgets, crash reservations, uncertain
outcomes, no POST retry and scoped WebSocket recovery. A loopback server exercises
an actual WebSocket handshake using synthetic messages.

The optional event bridge and local review queue add tests for dry-run defaults,
feedback isolation, fresh/scoped input, bounded sends, shared safeguards, durable
cases, priority ordering and explicit review before follow-up/closure. Four saved
native review events were also replayed into the local queue; four repeats were
deduplicated. Live motion observation produced no input during two 120-second
dry runs, so automatic initiation has synthetic coverage rather than live proof.
See [WORKFLOW.md](WORKFLOW.md) for operation and validation boundaries.

## Evaluation scope

The complete exploration comprised eight requests: three direct gateway
challenges and five native requests. Across those runs, five bookmarks and four
alarms were observed. Two exploratory railway responses returned RAIL_CLEAR
inconsistent with reviewed imagery; railway is outside the presented gate and
sidewalk workflows. Its native request produced a bookmark and no positive-token
alarm. Operators must not infer safety from an absent alarm.

These are repeated organizer clips, not an independent accuracy study. Gate
intent/successful entry and pedestrian detouring were not verified; the review
workflow asks the operator to inspect footage and confirm the circumstances.
Synthetic protocol tests establish the documented software behavior, while the
recorded native flows establish the lab integration.

The setup script was verified against the installed p042 configuration.
[Judge access instructions](JUDGE_ACCESS.md) describe how to inspect the native
summaries, bookmarks and alarms.
