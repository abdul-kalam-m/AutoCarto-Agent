"""CDC PLACES connector — Blueprint §6.1.

Unlike the Census ACS API, CDC PLACES' Socrata endpoint needs no API key
for this query volume — verified against the live endpoint. Tract-level
health measures (asthma, obesity, diabetes, etc.) for the whole country
live in one Socrata resource per release year; this module queries it
filtered to specific counties.
"""

from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Sequence

DEFAULT_BASE_URL = "https://data.cdc.gov/resource/cwsq-ngmh.json"  # PLACES 2023 census-tract release


def fetch_cdc_places_measure(
    measure_id: str,
    county_fips: Sequence[str],
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 30,
) -> Dict[str, Optional[float]]:
    """Fetch one CDC PLACES measure (crude prevalence, %) for all tracts
    in the given counties.

    Args:
        measure_id: PLACES measure code, e.g. "CASTHMA" (current asthma
            among adults)
        county_fips: five-digit county FIPS codes, e.g. ["13121", "13089"]

    Returns:
        {GEOID: crude_prevalence_percent}. GEOIDs with no BRFSS-based
        estimate (typically zero-population tracts) are simply absent —
        CDC PLACES does not emit a sentinel row for them, unlike ACS.
    """
    where_clause = "countyfips in (" + ",".join(f"'{c}'" for c in county_fips) + ")"
    params = {
        "$where": where_clause,
        "measureid": measure_id,
        "$limit": 1000,
        "$select": "locationid,data_value,totalpopulation",
    }
    url = base_url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "CartoLLM/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    return _parse_rows(rows)


def _parse_rows(rows: list) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for row in rows:
        value = row.get("data_value")
        out[row["locationid"]] = float(value) if value not in (None, "") else None
    return out


def load_cdc_places_snapshot(csv_path: Path) -> Dict[str, Optional[float]]:
    """Load a pre-fetched CDC PLACES snapshot CSV into a {GEOID: value}
    dict. See data/MANIFEST.md for provenance."""
    out: Dict[str, Optional[float]] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            value = row.get("data_value")
            out[row["locationid"]] = float(value) if value not in (None, "") else None
    return out
