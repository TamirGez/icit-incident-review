# Recorded gateway completion timing

The presented gate workflow has three native requests with completion times of
**14.637, 15.070 and 15.773 seconds**: median **15.070 s**, displayed as **15.1 s**.

Timing is gateway `CreationTimeUtc` to `LastUpdatedTimeUtc` for a Completed request.
It includes the 10-second post-buffer wait. Native alarm/event timestamps are
backdated to the clip start, so this metric uses gateway timestamps rather than
alarm timestamps. It measures request completion, not operator handling time.

## Per-run timing

| Native request | Gateway completion seconds |
|---|---:|
| Gate 1 | 14.637 |
| Gate 2 | 15.070 |
| Gate 3 | 15.773 |
| Sidewalk | 15.209 |
| Railway exploration | 15.342 |

Across all five native requests, median completion is 15.209 seconds. The gate
subset is used in the presentation because gate review is the primary use case.
The three initial direct challenges have no comparable native timing value.

## Recompute

```bash
python scripts/evaluate.py
```

[measurements.csv](measurements.csv) contains scenario aliases, response
tokens and elapsed durations. The script reports the complete recorded evaluation;
filter its CSV to `scenario=gate, route=native` for the three gate timings above.
Expected tokens were assigned after reviewing visible activity. Clips were
repeated rather than sampled independently; token counts describe these runs.
The [test record](RESULTS.md) documents the complete scenario outcomes and scope.
