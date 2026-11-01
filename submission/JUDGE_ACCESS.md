# View the running solution

The working system is installed on the assigned organizer lab **p042**, accessible
to authorized judges on the organizer Tailscale network. The public video shows
the real lab; it is not a public service endpoint. No lab credentials are included.

1. Use organizer-provided access to p042 through Remote Desktop.
2. Open XProtect Smart Client and sign in with your authorized account.
3. Open **Summarization → History**. The final native tests on 1 November 2026
   are gate at **20:07:09 UTC**, sidewalk at **20:08:41 UTC**, and railway at
   **20:10:00 UTC**. The recorded lab UI uses UTC. Verify the viewer's timezone.
4. Select the request to inspect its camera, Webhook trigger, Completed status,
   clip bounds, exact Hafnia answer and recording.
5. In **Alarm Manager**, inspect the matching ICIT_TEST_GATE_REVIEW and
   ICIT_TEST_SIDEWALK_REVIEW entries. In **Search → Bookmarks**, select the
   matching camera to see the full AI-labelled answer and bounded recording.

The three ICIT_TEST_* native input rules remain configured. The connector can
be run from an authorized Linux environment on the same organizer network using
[REPRODUCE.md](REPRODUCE.md). It requires the scoped basic account; obtain access
through the participant or organizer, never through public source code. A new
request must be fresh and respect the ledger's cooldown, shared cap and review
halt. Existing history can be inspected without consuming another analysis.

The Windows system and native rules are the running solution. The connector is
a command-line client, not a permanently running public web application. Local
VM uptime depends on the participant workstation. Organizer lab availability,
recording retention and judge network access remain external dependencies.

See [results and validation](RESULTS.md) for the known railway failure and test limits.

## Durable public evidence and optional review tools

The lab recording retention observed during setup was **24 hours**. Older clips
may expire even when summary/history or alarm records remain. The public 2:45
video preserves the demonstrated footage and result; do not assume old timestamps
remain playable. A fresh run needs authorized access and quota/freshness checks.

The public page also offers a labelled browser replay of a gate review case.
The new event bridge and local review queue are documented in [WORKFLOW.md](WORKFLOW.md).
They are optional CLI tools, not an unattended installed service. Automatic
initiation has synthetic coverage but did not receive a live input in the bounded
gate observation checks. The native p042 configuration remains the proven path.
