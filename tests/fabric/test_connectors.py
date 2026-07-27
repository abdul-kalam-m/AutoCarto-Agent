"""Real-data connector tests — Blueprint §6.1.

Parsing logic is tested against small, hand-crafted response fixtures
matching each API's exact real shape (verified against the live
endpoints during development — see data/MANIFEST.md), not live network
calls in the default test run. Snapshot-loading is tested against the
actual checksummed files in data/.
"""

from __future__ import annotations

from pathlib import Path

from autocarto.data_fabric.connectors.acs import (
    CENSUS_SENTINEL_MISSING,
    _parse_rows as parse_acs_rows,
    load_acs_snapshot,
)
from autocarto.data_fabric.connectors.cdc_places import (
    _parse_rows as parse_cdc_rows,
    load_cdc_places_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ACS_SNAPSHOT = REPO_ROOT / "data" / "acs_median_household_income_2022.csv"
CDC_SNAPSHOT = REPO_ROOT / "data" / "cdc_places_asthma_2023.csv"


# ── ACS connector: parsing logic (canned response, real API shape) ──────────

def test_acs_parse_rows_extracts_geoid_and_value():
    # Real Census API response shape: list of lists, header row first.
    raw = [
        ["B19013_001E", "NAME", "state", "county", "tract"],
        ["160500", "Census Tract 201; DeKalb County; Georgia", "13", "089", "020100"],
        ["105000", "Census Tract 202; DeKalb County; Georgia", "13", "089", "020200"],
    ]
    result = parse_acs_rows(raw, "B19013_001E")
    assert result == {"13089020100": 160500.0, "13089020200": 105000.0}


def test_acs_parse_rows_converts_sentinel_to_none():
    raw = [
        ["B19013_001E", "NAME", "state", "county", "tract"],
        [str(CENSUS_SENTINEL_MISSING), "Census Tract 9800; DeKalb County; Georgia", "13", "089", "980000"],
    ]
    result = parse_acs_rows(raw, "B19013_001E")
    assert result["13089980000"] is None


def test_acs_load_snapshot_matches_manifest_row_count():
    data = load_acs_snapshot(ACS_SNAPSHOT)
    assert len(data) == 530


def test_acs_snapshot_sentinel_tracts_are_none():
    data = load_acs_snapshot(ACS_SNAPSHOT)
    # The two county-level non-residential "Tract 9800" entries.
    assert data["13089980000"] is None
    assert data["13121980000"] is None


def test_acs_snapshot_known_value_matches_fetched_data():
    """Spot-check one value captured during the real fetch (DeKalb Tract 201)."""
    data = load_acs_snapshot(ACS_SNAPSHOT)
    assert data["13089020100"] == 160500.0


# ── CDC PLACES connector: parsing logic (canned response, real API shape) ───

def test_cdc_parse_rows_extracts_locationid_and_value():
    raw = [
        {"locationid": "13089023331", "data_value": "12.9", "totalpopulation": "3577"},
        {"locationid": "13121011647", "data_value": "8.8", "totalpopulation": "5160"},
    ]
    result = parse_cdc_rows(raw)
    assert result == {"13089023331": 12.9, "13121011647": 8.8}


def test_cdc_load_snapshot_covers_528_of_530_tracts():
    data = load_cdc_places_snapshot(CDC_SNAPSHOT)
    assert len(data) == 528  # 2 non-residential tracts have no BRFSS estimate


def test_cdc_snapshot_excludes_nonresidential_tracts_entirely():
    """CDC PLACES doesn't emit a sentinel row for zero-population tracts
    (unlike ACS) -- they're simply absent from the dict."""
    data = load_cdc_places_snapshot(CDC_SNAPSHOT)
    assert "13089980000" not in data
    assert "13121980000" not in data


def test_cdc_snapshot_known_value_matches_fetched_data():
    data = load_cdc_places_snapshot(CDC_SNAPSHOT)
    assert data["13089023331"] == 12.9
