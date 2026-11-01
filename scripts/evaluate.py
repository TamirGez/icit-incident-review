"""Recompute the small recorded demonstration's measurements without lab access."""
import csv
import json
import statistics
from pathlib import Path


def evaluate(path):
    with Path(path).open(newline="") as f:
        rows = list(csv.DictReader(f))
    timings = [float(r["gateway_elapsed_seconds"]) for r in rows if r["gateway_elapsed_seconds"]]
    scenarios = {}
    for row in rows:
        bucket = scenarios.setdefault(row["scenario"], {"runs": 0, "token_agreements": 0})
        bucket["runs"] += 1
        bucket["token_agreements"] += row["expected_token"] == row["observed_token"]
    return {"recorded_requests": len(rows), "scenarios": scenarios,
            "gateway_completion_seconds": {"n": len(timings), "min": min(timings),
                "median": statistics.median(timings), "max": max(timings)},
            "negative_control_clips": 0, "false_alarm_rate": None,
            "operator_time_saved_seconds": None,
            "limitations": ["Repeated organizer clips; not independent or blind evaluation",
                "Reference labels assigned by reviewing visible activity",
                "Gateway creation to final Completed update, including post-buffer wait",
                "No measured end-to-end alarm latency or operator time saving",
                "No negative controls: false-alarm rate cannot be estimated"]}


if __name__ == "__main__":
    print(json.dumps(evaluate(Path(__file__).resolve().parents[1] / "submission/measurements.csv"), indent=2))
