#!/usr/bin/env python3
"""Sanity-gate the freshly generated data before it is allowed to publish.

Exits non-zero (which fails the workflow, so nothing deploys) if the data looks
broken. Thresholds are deliberately loose: they catch a catastrophic or empty
regeneration, NOT normal week-to-week or engineering-works variation. Tune the
floors if your real numbers ever legitimately dip near them.
"""
import csv
import json
import sys
from collections import Counter

def fail(msg):
    print(f"VALIDATION FAILED: {msg}")
    sys.exit(1)

# ---- version.json counts ----
try:
    v = json.load(open("data/version.json"))
except Exception as e:
    fail(f"cannot read version.json: {e}")

floors = [
    ("trips_count",          8000),
    ("stop_times_count",     150000),
    ("stations_count",       100),
    ("schedule_departures",  100000),
    ("service_dates",        1),
]
for key, floor in floors:
    got = v.get(key, 0)
    if got < floor:
        fail(f"{key}={got} is below floor {floor}")

# ---- all seven T-bana lines, both directions, present with real stations ----
try:
    st = json.load(open("data/tbana_stations.json"))
except Exception as e:
    fail(f"cannot read tbana_stations.json: {e}")

EXPECTED_LINES = {10, 11, 13, 14, 17, 18, 19}
lines = {s["line"] for s in st}
missing = EXPECTED_LINES - lines
if missing:
    fail(f"missing lines {sorted(missing)} (have {sorted(lines)})")

per_dir = Counter((s["line"], s["direction"]) for s in st)
for ln in sorted(EXPECTED_LINES):
    for d in (0, 1):
        n = per_dir[(ln, d)]
        if n < 3:
            fail(f"line {ln} direction {d} has only {n} stations")

# ---- stop_times file parses and has data rows ----
try:
    with open("data/tbana_stop_times.csv", newline="") as f:
        r = csv.reader(f)
        header = next(r, None)
        first = next(r, None)
    if not header or first is None:
        fail("tbana_stop_times.csv missing header or data rows")
except Exception as e:
    fail(f"cannot read tbana_stop_times.csv: {e}")

print("Validation OK:", json.dumps(v))
