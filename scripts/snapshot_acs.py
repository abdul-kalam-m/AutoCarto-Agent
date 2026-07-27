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

OUT_CSV = REPO_ROOT / "data" / "acs_median_household_income_2022.csv"
COMMITTED_SHA256 = "00dcf4d5f955cc39d3f7b9325846023a0d7a6e7eab535d95ad9456636e79c63e"

YEAR = 2022
DATASET = "acs/acs5"
VARIABLE = "B19013_001E"
STATE_FIPS = "13"
COUNTY_FIPS = ("089", "121")  # DeKalb, Fulton


def fetch_rows(api_key: str) -> list[dict]:
    rows: list[dict] = []
    for county in COUNTY_FIPS:
        params = {
            "get": f"{VARIABLE},NAME",
            "for": "tract:*",
            "in": f"state:{STATE_FIPS}+county:{county}",
            "key": api_key,
        }
        url = f"https://api.census.gov/data/{YEAR}/{DATASET}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "CartoLLM/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        header = raw[0]
        vi, ni = header.index(VARIABLE), header.index("NAME")
        si, ci, ti = header.index("state"), header.index("county"), header.index("tract")
        for r in raw[1:]:
            rows.append({
                "GEOID": _geoid(r[si], r[ci], r[ti]),
                "NAME": r[ni],
                VARIABLE: r[vi],
            })
    rows.sort(key=lambda d: d["GEOID"])
    return rows


def write_csv(rows: list[dict]) -> bytes:
    # newline="" so csv writes its default \r\n terminator, matching the
    # committed file byte-for-byte (it was originally generated on Windows).
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=["GEOID", "NAME", VARIABLE])
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def main() -> int:
    api_key = get_key("CENSUS_API_KEY")
    print(f"Fetching ACS {VARIABLE} for state {STATE_FIPS}, counties {COUNTY_FIPS}...")
    rows = fetch_rows(api_key)
    print(f"  -> {len(rows)} tract rows")

    data = write_csv(rows)
    digest = hashlib.sha256(data).hexdigest()

    OUT_CSV.write_bytes(data)
    print(f"Wrote {OUT_CSV} ({len(rows)} rows, {len(data)} bytes)")
    print(f"SHA-256: {digest}")

    if digest == COMMITTED_SHA256:
        print("MATCH: byte-identical to the committed snapshot. Reproducibility confirmed.")
        return 0
    print("DIFFERS from the committed snapshot's SHA-256 "
          f"({COMMITTED_SHA256}). The Census service may have revised the "
          "2022 vintage, or the NAME formatting changed. Inspect the diff "
          "and re-verify any published statistics before reusing.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
