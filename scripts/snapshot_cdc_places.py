#!/usr/bin/env python3
"""Snapshot CDC PLACES asthma prevalence for Fulton + DeKalb Counties, GA.

Unlike the Census ACS API, CDC PLACES' Socrata endpoint needs no API key
for this query volume (verified: a plain unauthenticated GET returns real
data). Run this to regenerate data/cdc_places_asthma_2023.csv:

    python scripts/snapshot_cdc_places.py

Dataset: PLACES: Census Tract Data (GIS Friendly Format), 2023 release
Socrata resource ID: cwsq-ngmh (see https://data.cdc.gov/d/cwsq-ngmh)
Measure: CASTHMA (Current asthma among adults, crude prevalence, BRFSS)
"""

from __future__ import annotations

import csv
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = REPO_ROOT / "data" / "cdc_places_asthma_2023.csv"
MANIFEST = REPO_ROOT / "data" / "MANIFEST.md"

BASE_URL = "https://data.cdc.gov/resource/cwsq-ngmh.json"
FIPS_COUNTIES = ("13121", "13089")  # Fulton, DeKalb


def fetch() -> list[dict]:
    params = {
        "$where": f"countyfips in ({','.join(repr(c) for c in FIPS_COUNTIES)})".replace("'", "'"),
        "measureid": "CASTHMA",
        "$limit": 1000,
        "$select": "locationid,countyname,data_value,low_confidence_limit,"
                   "high_confidence_limit,totalpopulation,year,datasource",
    }
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "CartoLLM/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    print("Fetching CDC PLACES asthma prevalence (Fulton + DeKalb, GA)...")
    rows = fetch()
    print(f"  -> {len(rows)} tract records")

    rows.sort(key=lambda r: r["locationid"])
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["locationid", "countyname", "data_value", "low_confidence_limit",
                  "high_confidence_limit", "totalpopulation", "year", "datasource"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    digest = hashlib.sha256(OUT_CSV.read_bytes()).hexdigest()
    print(f"Wrote {OUT_CSV} ({len(rows)} rows)")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
