"""Tier 3 Metadata Quality Gate — Blueprint §6.2 C7''.

7-point STAC-item completeness rubric (1 point each): title, description,
declared variable names, declared units, temporal extent, license,
lineage. Old-abstract / poster Tier 3 semantics ("Metadata Quality Gate"):

    6-7 points -> TRUSTED  : proceed directly, no profiling needed
    3-5 points -> AUGMENT  : profile a data sample (up to
                              PROFILE_SAMPLE_ROWS) to fill the gaps the
                              catalog metadata alone doesn't answer
    0-2 points -> REJECT   : insufficiency report; do not use this item

This is deliberately a *metadata* score, not a data-quality score: it
answers "can we trust what the catalog claims about this dataset" before
any bytes of the dataset itself are touched — the profiler (below) is what
touches actual data, and only for the AUGMENT bucket.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from autocarto.data_fabric.hybrid_retrieval import STACItem

MetadataBucket = Literal["TRUSTED", "AUGMENT", "REJECT"]

PROFILE_SAMPLE_ROWS = 1000
TRUSTED_MIN = 6
AUGMENT_MIN = 3

# Placeholder-ish titles that shouldn't count as "has a real title".
_GENERIC_TITLE_MARKERS = {"untitled", "data", "dataset", "sensor data", "unknown", ""}
_MIN_DESCRIPTION_LEN = 20  # characters; excludes one-word placeholders


@dataclass
class MetadataScoreResult:
    item_id: str
    score: int  # 0-7
    bucket: MetadataBucket
    checklist: Dict[str, bool]
    missing: List[str]
    instruction: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "score": self.score,
            "bucket": self.bucket,
            "checklist": self.checklist,
            "missing": self.missing,
            "instruction": self.instruction,
        }


class MetadataScorer:
    """Scores a STACItem's metadata completeness on the 7-point rubric."""

    def score(self, item: STACItem) -> MetadataScoreResult:
        checklist = {
            "title": self._has_title(item),
            "description": self._has_description(item),
            "variable_names": self._has_variable_names(item),
            "units": self._has_units(item),
            "temporal_extent": self._has_temporal_extent(item),
            "license": bool(item.license),
            "lineage": bool(item.lineage),
        }
        score = sum(checklist.values())
        bucket = self._bucket_for(score)
        missing = [k for k, v in checklist.items() if not v]
        return MetadataScoreResult(
            item_id=item.id, score=score, bucket=bucket,
            checklist=checklist, missing=missing,
            instruction=self._instruction_for(bucket, missing),
        )

    @staticmethod
    def _has_title(item: STACItem) -> bool:
        return (item.title or "").strip().lower() not in _GENERIC_TITLE_MARKERS

    @staticmethod
    def _has_description(item: STACItem) -> bool:
        return len((item.description or "").strip()) >= _MIN_DESCRIPTION_LEN

    @staticmethod
    def _has_variable_names(item: STACItem) -> bool:
        return bool(item.variables) and all(v.get("name") for v in item.variables)

    @staticmethod
    def _has_units(item: STACItem) -> bool:
        return bool(item.variables) and all(v.get("units") for v in item.variables)

    @staticmethod
    def _has_temporal_extent(item: STACItem) -> bool:
        return bool(item.temporal_start) and bool(item.temporal_end)

    @staticmethod
    def _bucket_for(score: int) -> MetadataBucket:
        if score >= TRUSTED_MIN:
            return "TRUSTED"
        if score >= AUGMENT_MIN:
            return "AUGMENT"
        return "REJECT"

    @staticmethod
    def _instruction_for(bucket: MetadataBucket, missing: List[str]) -> str:
        if bucket == "TRUSTED":
            return "Metadata is sufficiently complete; proceed directly."
        if bucket == "AUGMENT":
            return (
                f"Metadata is incomplete ({', '.join(missing)} missing). "
                f"Profile up to {PROFILE_SAMPLE_ROWS} sample rows to fill "
                f"the gaps before use."
            )
        return (
            f"Metadata is too sparse to trust ({', '.join(missing)} "
            f"missing). Do not use this dataset without human review."
        )


class DataProfiler:
    """Samples rows to augment sparse metadata — the AUGMENT bucket's remedy.

    Deliberately dumb: infers dtype/cardinality/null-rate/numeric range
    from a bounded sample, nothing more. It exists to answer the specific
    questions a low metadata score leaves open (are there real units? is
    this actually numeric? how sparse is it?), not to replace the catalog.
    """

    def profile(self, rows: Any, max_rows: int = PROFILE_SAMPLE_ROWS) -> Dict[str, Any]:
        import pandas as pd

        if not isinstance(rows, pd.DataFrame):
            rows = pd.DataFrame(rows)
        sample = rows.head(max_rows)

        columns: Dict[str, Any] = {}
        for col in sample.columns:
            series = sample[col]
            is_numeric = pd.api.types.is_numeric_dtype(series)
            columns[col] = {
                "dtype": str(series.dtype),
                "n_unique": int(series.nunique()),
                "n_null": int(series.isna().sum()),
                "min": float(series.min()) if is_numeric and len(series) else None,
                "max": float(series.max()) if is_numeric and len(series) else None,
            }

        return {
            "sampled_rows": int(len(sample)),
            "total_rows": int(len(rows)),
            "truncated": len(rows) > max_rows,
            "columns": columns,
        }
