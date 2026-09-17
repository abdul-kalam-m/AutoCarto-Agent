"""Versioned, offline JSON contracts and deterministic structural diffs."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

MAX_DOCUMENT_BYTES = 1024 * 1024
VERSIONS = {"workspace": (2, "workspace"), "web-map-trace": (1, "webTrace"), "orchestrator-trace": (1, "orchestratorTrace")}
TIMING_KEYS = frozenset({"retrieval_time_ms", "spatial_filter_time_ms", "exact_refine_time_ms", "semantic_search_time_ms", "execution_time_ms"})


@lru_cache(maxsize=1)
def schema():
    return json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))


def _finite(value, depth=0):
    if depth > 64:
        raise ValueError("JSON nesting exceeds 64 levels")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _finite(item, depth + 1)


def validate_document(document):
    _finite(document)
    if not isinstance(document, dict):
        raise ValueError("Expected a JSON object")
    kind = document.get("kind")
    if kind is None:
        legacy_fields = {"version", "settings", "parks", "opacity", "outlines", "basemap", "plan", "sources", "messages"}
        if type(document.get("version")) is int and document["version"] == 1 and legacy_fields <= document.keys():
            raise ValueError("Legacy audit-only workspace v1 is not an importable workspace; export a versioned workspace from the original application")
        raise ValueError("Missing document kind; expected workspace, web-map-trace, or orchestrator-trace")
    if not isinstance(kind, str) or kind not in VERSIONS:
        raise ValueError("Unsupported document kind; expected workspace, web-map-trace, or orchestrator-trace")
    version, definition = VERSIONS[kind]
    if kind == "workspace" and type(document.get("version")) is int and document["version"] == 3:
        version, definition = 3, "workspaceV3"
    if type(document.get("version")) is not int or document["version"] != version:
        raise ValueError(f"Unsupported {kind} version; this application supports version {version}")
    contract = {"$ref": f"#/$defs/{definition}", "$defs": schema()["$defs"]}
    error = next(Draft202012Validator(contract).iter_errors(document), None)
    if error:
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        # Do not echo arbitrary imported content in user-facing errors.
        raise ValueError(f"Invalid document at {path}: failed {error.validator} constraint")
    return document


def parse_document(raw: bytes):
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("Workspace/trace exceeds 1 MiB")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON object keys are not allowed")
            result[key] = value
        return result
    try:
        document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Invalid UTF-8 JSON document") from None
    return validate_document(document)


def differences(left, right, *, ignore_timing=False, path=""):
    """Stable JSON-pointer differences; no float tolerance or ignored metadata by default."""
    if isinstance(left, dict) and isinstance(right, dict):
        changes = []
        for key in sorted(left.keys() | right.keys()):
            if ignore_timing and key in TIMING_KEYS:
                continue
            pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in left:
                changes.append({"path": pointer, "change": "added", "after": right[key]})
            elif key not in right:
                changes.append({"path": pointer, "change": "removed", "before": left[key]})
            else:
                changes.extend(differences(left[key], right[key], ignore_timing=ignore_timing, path=pointer))
        return changes
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [change for i, (a, b) in enumerate(zip(left, right)) for change in differences(a, b, ignore_timing=ignore_timing, path=f"{path}/{i}")]
    if type(left) in (int, float) and type(right) in (int, float) and left == right:
        return []
    if type(left) is not type(right) or left != right:
        return [{"path": path or "/", "change": "changed", "before": left, "after": right}]
    return []
