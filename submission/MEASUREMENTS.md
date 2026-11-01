# Recorded measurements and repeatable evaluation

Five native requests completed in **14.637–15.773 seconds**, median **15.209 s**.
This is gateway `CreationTimeUtc` to `LastUpdatedTimeUtc` for a Completed request,
including the 10-second post-buffer wait. It is not inference-only latency,
end-to-end alarm delivery latency, or operator handling time. Native alarm/event
timestamps are backdated to the clip start and cannot measure delivery latency.

The small [measurements.csv](measurements.csv) publishes scenario aliases, tokens
and elapsed durations only. It excludes actual camera/event/request IDs, private
configuration and full live responses. The original exports are retained locally.

```bash
python scripts/evaluate.py
```

| Scenario | Matching expected token / recorded requests | Native completion seconds |
|---|---:|---|
| Gate interaction | 4 / 4 | 14.637, 15.070, 15.773 |
| Sidewalk obstruction | 2 / 2 | 15.209 |
| Railway intrusion | 0 / 2 | 15.342 |

Expected tokens were assigned after reviewing the visible activity. The railway
reference includes the person at the platform edge with legs toward the track
bed; both model answers described the tracks as clear. Gate intent/successful
entry and pedestrian detouring were not verified and are excluded from agreement.

These are repeated organizer clips, three scenarios and eight requests, not
independent samples or a blind benchmark. The three direct challenges do not
have a comparable native timing value. All eight reference cases are positive;
there are **zero negative control clips**. False-positive rate, specificity and
false-alarm rate therefore cannot be estimated. No timed operator comparison
was conducted, so **time saved is unmeasured**. The review flow provides a
concrete workflow to evaluate in a future controlled study, not a claimed saving.

The filmed integration produced five native bookmarks and four alarms. Final
live duplicate checks for all three scenarios sent no further event POST.
Synthetic tests cover failure handling separately and are not accuracy evidence.

To extend this evaluation, obtain authorized negative and uncertain clips, label
them independently before testing, retain each request outcome (including errors),
and measure receipt times using one monotonic clock. Compare operators on the
same randomized task set with and without the review aid. Those studies have not
been performed for this submission.
