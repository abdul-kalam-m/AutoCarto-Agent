"""Metadata Quality Gate tests — Blueprint §6.2 C7'' 7-point rubric.

Fixtures are hand-labeled: each STACItem is built to hit an exact,
predictable score so the TRUSTED/AUGMENT/REJECT boundaries (6 and 3) are
tested precisely, not just "roughly high/low".
"""

from __future__ import annotations

import pandas as pd
import pytest

from autocarto.data_fabric.hybrid_retrieval import STACItem
from autocarto.data_fabric.metadata_scorer import (
    AUGMENT_MIN,
    DataProfiler,
    MetadataScorer,
    PROFILE_SAMPLE_ROWS,
    TRUSTED_MIN,
)

FULL_ITEM_KWARGS = dict(
    id="full", title="Atlanta Tree Canopy Loss 2015-2022",
    description="Annual tree canopy cover loss per census tract in metro Atlanta, derived from NLCD imagery.",
    bbox=[-84.6, 33.6, -84.2, 34.0],
    temporal_start="2015-01-01", temporal_end="2022-12-31",
    variables=[{"name": "canopy_loss_pct", "units": "percent"}],
    collection="nlcd", license="CC-BY-4.0",
    lineage="Derived from NLCD 30m raster via zonal statistics per tract.",
)


def test_all_seven_criteria_met_scores_7_trusted():
    item = STACItem(**FULL_ITEM_KWARGS)
    res = MetadataScorer().score(item)
    assert res.score == 7
    assert res.bucket == "TRUSTED"
    assert res.missing == []


def test_score_exactly_6_is_trusted_boundary():
    kwargs = dict(FULL_ITEM_KWARGS)
    kwargs["lineage"] = None  # drop exactly one point -> 6
    item = STACItem(**kwargs)
    res = MetadataScorer().score(item)
    assert res.score == 6
    assert res.bucket == "TRUSTED"


def test_score_exactly_5_is_augment_boundary():
    kwargs = dict(FULL_ITEM_KWARGS)
    kwargs["lineage"] = None
    kwargs["license"] = None  # drop two points -> 5
    item = STACItem(**kwargs)
    res = MetadataScorer().score(item)
    assert res.score == 5
    assert res.bucket == "AUGMENT"
    assert "AUGMENT" in res.bucket
    assert str(PROFILE_SAMPLE_ROWS) in res.instruction


def test_score_exactly_3_is_augment_lower_boundary():
    item = STACItem(
        id="sparse", title="CDC PLACES Asthma Rate", description="", bbox=[0, 0, 1, 1],
        temporal_start="2022-01-01", temporal_end="2022-12-31",
        variables=[{"name": "asthma_rate"}],  # name present, no units
    )
    res = MetadataScorer().score(item)
    # title(1) + temporal(1) + variable_names(1) = 3; no description/units/license/lineage
    assert res.score == 3
    assert res.bucket == "AUGMENT"


def test_score_exactly_2_is_reject_boundary():
    item = STACItem(
        id="thin", title="Sensor data 2019", description="", bbox=[0, 0, 1, 1],
        variables=[{"name": "value"}],
    )
    res = MetadataScorer().score(item)
    # title(1, "sensor data 2019" isn't a bare generic marker) + variable_names(1) = 2
    assert res.score == 2
    assert res.bucket == "REJECT"


def test_empty_item_scores_0_reject():
    item = STACItem(id="empty", title="", description="", bbox=[0, 0, 0, 0])
    res = MetadataScorer().score(item)
    assert res.score == 0
    assert res.bucket == "REJECT"
    assert set(res.missing) == {
        "title", "description", "variable_names", "units",
        "temporal_extent", "license", "lineage",
    }


def test_generic_title_markers_do_not_count():
    for bad_title in ("Untitled", "data", "Dataset", "unknown", ""):
        item = STACItem(id="x", title=bad_title, description="", bbox=[0, 0, 1, 1])
        res = MetadataScorer().score(item)
        assert res.checklist["title"] is False, f"{bad_title!r} should not count as a real title"


def test_units_requires_every_variable_to_have_units():
    item = STACItem(
        id="partial-units", title="x", description="x" * 25, bbox=[0, 0, 1, 1],
        variables=[{"name": "a", "units": "percent"}, {"name": "b"}],  # b has no units
    )
    res = MetadataScorer().score(item)
    assert res.checklist["variable_names"] is True
    assert res.checklist["units"] is False


def test_result_serializes_to_dict():
    item = STACItem(**FULL_ITEM_KWARGS)
    d = MetadataScorer().score(item).to_dict()
    assert d["score"] == 7
    assert d["bucket"] == "TRUSTED"


# ── DataProfiler (AUGMENT bucket's remedy) ────────────────────────────────────

def test_profiler_summarizes_dataframe():
    df = pd.DataFrame({
        "canopy_loss_pct": [1.2, 5.5, None, 30.0, 12.1],
        "tract_id": ["A", "B", "C", "D", "E"],
    })
    profile = DataProfiler().profile(df)
    assert profile["sampled_rows"] == 5
    assert profile["total_rows"] == 5
    assert profile["truncated"] is False
    assert profile["columns"]["canopy_loss_pct"]["n_null"] == 1
    assert profile["columns"]["canopy_loss_pct"]["min"] == 1.2
    assert profile["columns"]["canopy_loss_pct"]["max"] == 30.0
    assert profile["columns"]["tract_id"]["min"] is None  # non-numeric


def test_profiler_truncates_and_flags_large_input():
    df = pd.DataFrame({"x": list(range(PROFILE_SAMPLE_ROWS + 500))})
    profile = DataProfiler().profile(df)
    assert profile["sampled_rows"] == PROFILE_SAMPLE_ROWS
    assert profile["total_rows"] == PROFILE_SAMPLE_ROWS + 500
    assert profile["truncated"] is True


def test_profiler_accepts_plain_dict_of_lists():
    profile = DataProfiler().profile({"a": [1, 2, 3]})
    assert profile["sampled_rows"] == 3
