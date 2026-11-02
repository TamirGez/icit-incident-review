# View the running solution

The native XProtect and Hafnia workflow is configured on **p042** in the organizer
Tailscale network. Use the organizer-provided Remote Desktop and XProtect accounts.

1. Connect to p042 and open **XProtect Smart Client**.
2. Open **Summarization → History**. The recorded native requests on 1 November
   2026 are gate at **20:07:09 UTC** and sidewalk at **20:08:41 UTC**. Check the
   viewer's timezone when locating them.
3. Select a request to inspect its camera, Webhook trigger, Completed status,
   clip bounds and Hafnia answer.
4. In **Alarm Manager**, inspect the matching `ICIT_TEST_GATE_REVIEW` and
   `ICIT_TEST_SIDEWALK_REVIEW` entries.
5. In **Search → Bookmarks**, select the corresponding camera and inspect the
   AI-labelled answer and recording interval.

## Recorded demonstration

[Watch the 2:45 demo](https://tamirgez.github.io/icit-incident-review/).

The lab recording retention is **24 hours**. Older media may expire while
history and alarm records remain. The video preserves the demonstrated footage
and results. Its interactive review panel uses illustrative operator actions.

## Run a fresh request

The command-line connector runs from an authorized Linux client on the same
organizer network. Follow [Installation and configuration](REPRODUCE.md) using
the scoped basic account. Requests must be fresh and respect the shared ledger,
request cap, cooldown and review halt. Inspect the gateway quota before sending.

[Operator workflow](WORKFLOW.md) · [Results and validation](RESULTS.md)
