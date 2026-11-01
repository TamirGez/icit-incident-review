# Results and validation — 1 November 2026

| Scenario | Observed outcome |
|---|---|
| School gate | Four GATE_INTERACTION summaries; three native bookmarks and three review alarms |
| Sidewalk | Two SIDEWALK_BLOCKED summaries; one native bookmark and one review alarm |
| Railway | Two incorrect RAIL_CLEAR summaries; one native bookmark and no positive-token alarm |

Eight Hafnia requests completed: three initial direct gateway challenges and
five native webhook requests initiated by the connector. Four operator alarms
and five native bookmarks were observed. Final duplicate requests for all three
scenarios were suppressed without another event POST. All triggers were manual.
The demo is authentic Smart Client playback with labelled cuts; it does not
claim uninterrupted real-time latency or automatic private-plugin inference.

Gate interaction and a fallen scooter are visible. The model's claim of intent
to open the gate and its claim about pedestrians detouring were not independently
validated. The railway clear answers conflict with reviewed imagery. These
alarms are operator review requests, not authoritative scene determinations.

## Verification scope

The 41-test public suite covers timestamp validation, scoped authentication,
REST response handling, pagination, duplicate persistence, cooldown/shared
budgets, crash reservations, uncertain outcomes, no POST retry, and WebSocket
scoping/session recovery. A loopback server exercises an actual WebSocket
handshake using synthetic messages. All 41 tests passed on the host and the
isolated Ubuntu guest for this reduced publication variant.

The native live path passed for gate and sidewalk. The setup script rerun
verified the three installed configurations. Two early gate requests succeeded
remotely but halted locally on an unexpected zero-UUID receipt; histories were
reviewed before resuming and the parser was corrected. They remain counted.

A clean-machine rebuild, deliberately induced live outages/restarts, production
reliability, broad accuracy, private-engine inference and performance benchmarks
were not tested. Synthetic failure tests do not prove live outage recovery.

Detailed event/camera/bookmark identifiers, full JSON answers and private runtime
logs are retained locally, not published. Authorized judges can inspect the
actual lab through [JUDGE_ACCESS.md](JUDGE_ACCESS.md). The public demo itself
shows organizer imagery and some visible lab names, times and summary metadata.
