"""Census ACS connector — Blueprint §6.1.

The ACS Data API requires a key for *every* request, including small ones
(verified: an unauthenticated request returns an HTML "Missing Key" error
page, unlike the TIGER geometry endpoint used elsewhere in this project).
``fetch_acs_variable`` therefore takes an explicit ``api_key`` — get a free
one at https://api.census.gov/data/key_signup.html — and is not called at
test time without one (see tests/fabric/test_connectors.py, which tests
the parsing logic against a canned response and skips the live call).

The Census Bureau's sentinel for "cannot be estimated" (typically a
zero-population tract) is the literal integer -666666666. This module
converts it to ``None`` rather than passing it through as a value a
caller might average or plot.
"""

from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Sequence

CENSUS_SENTINEL_MISSING = -666666666
DEFAULT_BASE_URL = "https://api.census.gov/data"


def _geoid(state: str, county: str, tract: str) -> str:
    return f"{int(state):02d}{int(county):03d}{int(tract):06d}"


def fetch_acs_variable(
    variable: str,
    state_fips: str,
    county_fips: Sequence[str],
    year: int,
    api_key: str,
    *,
    dataset: str = "acs/acs5",
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = 30,
) -> Dict[str, Optional[float]]:
    """Fetch one ACS variable for all tracts in the given counties.

    Args:
        variable: ACS variable code, e.g. "B19013_001E" (median household income)
        state_fips: two-digit state FIPS, e.g. "13" for Georgia
        county_fips: one or more three-digit county FIPS codes
        year: ACS 5-year vintage, e.g. 2022
        api_key: Census API key (required — see module docstring)
        dataset: API dataset path, default "acs/acs5"

    Returns:
        {GEOID: value}. Value is None where the Census sentinel
        (-666666666, "cannot be estimated") was returned.
    """
    results: Dict[str, Optional[float]] = {}
    for county in county_fips:
        params = {
            "get": f"{variable},NAME",
            "for": "tract:*",
            "in": f"state:{state_fips}+county:{county}",
            "key": api_key,
        }
        url = f"{base_url}/{year}/{dataset}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "CartoLLM/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            rows = json.loads(resp.read().decode("utf-8"))
        results.update(_parse_rows(rows, variable))
    return results


def _parse_rows(rows: list, variable: str) -> Dict[str, Optional[float]]:
    """Parse a raw Census API JSON response (list of lists; row 0 = header)."""
    if not rows:
        return {}
    header = rows[0]
    var_idx = header.index(variable)
    state_idx = header.index("state")
    county_idx = header.index("county")
    tract_idx = header.index("tract")

    out: Dict[str, Optional[float]] = {}
    for row in rows[1:]:
        raw_value = int(row[var_idx])
        geoid = _geoid(row[state_idx], row[county_idx], row[tract_idx])
        out[geoid] = None if raw_value == CENSUS_SENTINEL_MISSING else float(raw_value)
    return out


def load_acs_snapshot(csv_path: Path) -> Dict[str, Optional[float]]:
    """Load a pre-fetched ACS snapshot CSV (GEOID, NAME, <variable>) into
    a {GEOID: value} dict, applying the same sentinel-to-None handling as
    a live fetch. See data/MANIFEST.md for the snapshot's provenance."""
    out: Dict[str, Optional[float]] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        value_field = [c for c in reader.fieldnames if c not in ("GEOID", "NAME")][0]
        for row in reader:
            raw_value = int(row[value_field])
            out[row["GEOID"]] = None if raw_value == CENSUS_SENTINEL_MISSING else float(raw_value)
    return out
