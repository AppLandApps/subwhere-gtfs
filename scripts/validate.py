#!/usr/bin/env python3
"""Sanity-gate the freshly generated data before it is allowed to publish.

Exits non-zero (failing the workflow, so nothing deploys) if the data looks
broken. Design notes, learned the hard way:

  * ABSOLUTE floors are set to catch a COLLAPSE (empty/truncated feed), not to
    police normal variation. T-bana trip counts move a lot with the season —
    ~17k during summer engineering works, ~8.8k in late August, ~7.5k a day
    later — so a floor tuned to one month false-alarms in another. A gate that
    blocks for days is its own outage: nothing republishes, the static trip ids
    drift from the live feed, and trains start vanishing in the app.

  * The real signal is a RELATIVE cliff: today's data being a fraction of the
    last thing we successfully published. That catches a genuinely truncated
    feed while letting seasonal drift through. The previous published counts
    come from the committed version.json (git HEAD) — generate.py has already
    overwritten the working copy by the time this runs.

  * STRUCTURAL checks (all seven lines, both directions, parseable files) are
    the strongest guarantee and are always run.

  * Every check runs before exiting, so one failure doesn't mask the rest.
"""
import csv
import json
import subprocess
import sys
from collections import Counter

errors = []
notes = []

# ---- freshly generated counts ----
try:
    v = json.load(open("data/version.json"))
except Exception as e:
    print(f"VALIDATION FAILED: cannot read version.json: {e}")
    sys.exit(1)

# ---- absolute floors: collapse detection only, deliberately generous ----
COLLAPSE_FLOORS = [
    ("trips_count",          3000),
    ("stop_times_count",     60000),
    ("stations_count",       100),
    ("schedule_departures",  40000),
    ("service_dates",        1),
]
for key, floor in COLLAPSE_FLOORS:
    got = v.get(key, 0)
    if got < floor:
        errors.append(f"{key}={got} is below collapse floor {floor}")

# ---- relative check against the last SUCCESSFULLY PUBLISHED data ----
# A big single-day cliff means the upstream feed truncated; gradual seasonal
# decline passes. Skipped silently on the first run / if git history is absent.
MIN_FRACTION = 0.55
try:
    prev_raw = subprocess.run(
        ["git", "show", "HEAD:data/version.json"],
        capture_output=True, text=True, timeout=30,
    )
    if prev_raw.returncode == 0:
        prev = json.loads(prev_raw.stdout)
        for key in ("trips_count", "stop_times_count", "schedule_departures"):
            old, new = prev.get(key, 0), v.get(key, 0)
            if old > 0:
                frac = new / old
                notes.append(f"{key}: {old} -> {new} ({frac:.0%})")
                if frac < MIN_FRACTION:
                    errors.append(
                        f"{key} fell to {frac:.0%} of last published "
                        f"({old} -> {new}); looks truncated"
                    )
    else:
        notes.append("no previous version.json in git history — relative check skipped")
except Exception as e:
    notes.append(f"relative check skipped: {e}")

# ---- structural: all seven T-bana lines, both directions, real stations ----
EXPECTED_LINES = {10, 11, 13, 14, 17, 18, 19}
try:
    st = json.load(open("data/tbana_stations.json"))
    lines = {s["line"] for s in st}
    missing = EXPECTED_LINES - lines
    if missing:
        errors.append(f"missing lines {sorted(missing)} (have {sorted(lines)})")
    per_dir = Counter((s["line"], s["direction"]) for s in st)
    for ln in sorted(EXPECTED_LINES & lines):
        for d in (0, 1):
            n = per_dir[(ln, d)]
            if n < 3:
                errors.append(f"line {ln} direction {d} has only {n} stations")
except Exception as e:
    errors.append(f"cannot read tbana_stations.json: {e}")

# ---- structural: stop_times parses and has data rows ----
try:
    with open("data/tbana_stop_times.csv", newline="") as f:
        r = csv.reader(f)
        header = next(r, None)
        first = next(r, None)
    if not header or first is None:
        errors.append("tbana_stop_times.csv missing header or data rows")
except Exception as e:
    errors.append(f"cannot read tbana_stop_times.csv: {e}")

# ---- report ----
for n in notes:
    print(f"note: {n}")
print("counts:", json.dumps(v))

if errors:
    for e in errors:
        print(f"VALIDATION FAILED: {e}")
    sys.exit(1)

print("Validation OK")
