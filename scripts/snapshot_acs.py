#!/usr/bin/env python3
"""Snapshot Census ACS median household income for Fulton + DeKalb, GA.

Closes the reproducibility gap documented in data/MANIFEST.md: the ACS Data
API requires a key for every request (verified: an unauthenticated call
returns an HTML "Missing Key" page), so unlike the CDC PLACES snapshot
there was previously no standalone script to regenerate this file. This
script reads CENSUS_API_KEY from the environment or .env and regenerates
data/acs_median_household_income_2022.csv, then verifies the result against
the committed SHA-256.

    python scripts/snapshot_acs.py

Get a free key at https://api.census.gov/data/key_signup.html and put it in
.env as CENSUS_API_KEY=... (see .env.example). The .env file is gitignored.

Table B19013 = median household income in the past 12 months
(2022-inflation-adjusted dollars), ACS 5-Year 2022, tract level. The Census
sentinel -666666666 ("cannot be estimated", e.g. zero-population tracts) is
preserved verbatim in the CSV; loaders convert it to None at read time (see
data_fabric/connectors/acs.py).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from autocarto.data_fabric.connectors.acs import _geoid  # single source of GEOID padding
from autocarto.env import get_key

YEAR = 2022
DATASET = "acs/acs5"
STATE_FIPS = "13"
COUNTY_FIPS = ("089", "121")  # DeKalb, Fulton

# Known snapshots: ACS variable code -> (output filename, committed SHA-256).
# The SHA is the reproducibility contract for an already-pinned file; None
# means "not yet pinned", so the first run reports the digest to paste into
# data/MANIFEST.md rather than comparing against nothing.
SNAPSHOTS: dict[str, tuple[str, str | None]] = {
    "B19013_001E": (
        "acs_median_household_income_2022.csv",
        "00dcf4d5f955cc39d3f7b9325846023a0d7a6e7eab535d95ad9456636e79c63e",
    ),
    "B01003_001E": (
        "acs_total_population_2022.csv",
        "d3c0e6ff792c3863295192be055d8899be907e2c0f8e768183c154b8ff507307",
    ),
}
DEFAULT_VARIABLE = "B19013_001E"


def fetch_rows(api_key: str, variable: str = DEFAULT_VARIABLE) -> list[dict]:
    rows: list[dict] = []
    for county in COUNTY_FIPS:
        params = {
            "get": f"{variable},NAME",
            "for": "tract:*",
            "in": f"state:{STATE_FIPS}+county:{county}",
            "key": api_key,
        }
        url = f"https://api.census.gov/data/{YEAR}/{DATASET}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "CartoLLM/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        header = raw[0]
        vi, ni = header.index(variable), header.index("NAME")
        si, ci, ti = header.index("state"), header.index("county"), header.index("tract")
        for r in raw[1:]:
            rows.append({
                "GEOID": _geoid(r[si], r[ci], r[ti]),
                "NAME": r[ni],
                variable: r[vi],
            })
    rows.sort(key=lambda d: d["GEOID"])
    return rows


def write_csv(rows: list[dict], variable: str = DEFAULT_VARIABLE) -> bytes:
    # newline="" so csv writes its default \r\n terminator, matching the
    # committed file byte-for-byte (it was originally generated on Windows).
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=["GEOID", "NAME", variable])
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot one ACS variable for the Atlanta AOI.")
    parser.add_argument(
        "--variable", default=DEFAULT_VARIABLE, choices=sorted(SNAPSHOTS),
        help=f"ACS variable code (default: {DEFAULT_VARIABLE}, median household income)",
    )
    args = parser.parse_args(argv)

    variable = args.variable
    filename, committed_sha = SNAPSHOTS[variable]
    out_csv = REPO_ROOT / "data" / filename

    api_key = get_key("CENSUS_API_KEY")
    print(f"Fetching ACS {variable} for state {STATE_FIPS}, counties {COUNTY_FIPS}...")
    rows = fetch_rows(api_key, variable)
    print(f"  -> {len(rows)} tract rows")

    data = write_csv(rows, variable)
    digest = hashlib.sha256(data).hexdigest()

    out_csv.write_bytes(data)
    print(f"Wrote {out_csv} ({len(rows)} rows, {len(data)} bytes)")
    print(f"SHA-256: {digest}")

    if committed_sha is None:
        print("No committed SHA-256 recorded for this variable yet. Add the "
              "digest above to data/MANIFEST.md and to SNAPSHOTS in this "
              "script to make future runs self-verifying.")
        return 0
    if digest == committed_sha:
        print("MATCH: byte-identical to the committed snapshot. Reproducibility confirmed.")
        return 0
    print("DIFFERS from the committed snapshot's SHA-256 "
          f"({committed_sha}). The Census service may have revised the "
          "2022 vintage, or the NAME formatting changed. Inspect the diff "
          "and re-verify any published statistics before reusing.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
