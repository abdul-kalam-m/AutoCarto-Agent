"""Web map plans: schema-only intent, deterministic G2/G5, no code execution.

This adapter deliberately reports its narrower validation scope. A Web
Mercator exploration map is not the CLI's fully gated publication artifact.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import jenkspy
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from autocarto.contracts import AreaOfInterest, FieldSchema, SemanticContext, adapt_gate2
from autocarto.env import get_key
from autocarto.execution.gates.gate2_classification import ClassificationDiagnosticEngine
from autocarto.execution.gates.gate5_color_accessibility import ColorAccessibilityGate
from autocarto.offline import is_offline
from autocarto.semantic.nvidia_llm import NvidiaLLM

DATA = Path(__file__).parent / "data"
Metric = Literal["density", "population", "income"]
Palette = Literal["forest", "ocean", "violet", "sunset"]
Method = Literal["auto", "quantile", "jenks", "equal_interval"]
METRICS = {
    "density": {"name": "Population density", "unit": "people / sq mi", "description": "ACS population divided by NJOGIS county boundary area."},
    "population": {"name": "Total population", "unit": "people", "description": "ACS 5-year population estimates by county."},
    "income": {"name": "Household income", "unit": "USD", "description": "Median household income in 2023 inflation-adjusted dollars."},
}


class MapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Metric = "density"
    palette: Palette = "forest"
    method: Method = "auto"


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1500)
    current: MapRequest = Field(default_factory=MapRequest)
    parks: bool = False
    use_ai: bool = False


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["map", "style", "focus", "unsupported"] = "map"
    metric: Metric | None = None
    palette: Palette | None = None
    method: Method | None = None
    parks: bool | None = None
    county: str | None = Field(default=None, max_length=30)
    statewide: bool = False


@lru_cache(maxsize=4)
def read_data(name: str):
    if name not in {"manifest", "counties", "parks", "park_points"}:
        raise ValueError("Unknown dataset")
    path = DATA / (name + (".json" if name == "manifest" else ".geojson"))
    content = path.read_bytes()
    if name != "manifest":
        expected = read_data("manifest")["files"][path.name]["sha256"]
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Snapshot integrity check failed: {name}")
    return json.loads(content)


def catalog():
    manifest = read_data("manifest")
    counties = read_data("counties")["features"]
    parks = read_data("parks")["features"]
    return {
        "datasets": [
            {"id": key, **value, "count": len(counties), "geometry": "Polygon", "category": "Demographics", "source": "U.S. Census Bureau · NJOGIS", "vintage": "2019–2023 ACS", "url": manifest["sources"]["demographics"]}
            for key, value in METRICS.items()
        ] + [{"id": "parks", "name": "State-owned open space", "description": manifest["coverage"]["parks"], "unit": "areas", "count": len(parks), "geometry": "Polygon", "category": "Outdoors", "source": "NJDEP", "vintage": "Pinned " + manifest["retrieved_at"][:10], "url": manifest["sources"]["parks"]}, {"id": "park_points", "name": "Historical park locations", "description": manifest["coverage"]["park_points"], "unit": "locations", "count": len(read_data("park_points")["features"]), "geometry": "Point", "category": "Outdoors", "source": "NJDEP / GNIS", "vintage": "2016", "url": manifest["sources"]["park_points"]}],
        "manifest": manifest,
        "park_plan": park_plan(),
        "population": sum(f["properties"]["population"] for f in counties),
        "counties": [f["properties"] for f in counties],
        "ai_available": bool(get_key("NVIDIA_API_KEY", required=False)) and not is_offline(),
        "offline": is_offline(),
    }


@lru_cache(maxsize=1)
def park_plan():
    """Nominal FEATURE_CLASS colors, checked pairwise by G5 (no implied order)."""
    from itertools import combinations
    from collections import Counter
    counts = Counter(f["properties"]["FEATURE_CLASS"] or "__unspecified__" for f in read_data("parks")["features"])
    colors = {"Open Space": "#237d55", "__unspecified__": "#dedede"}
    if set(counts) - colors.keys():
        raise ValueError("New NJDEP FEATURE_CLASS values require a reviewed categorical palette")
    categories = [{"value": value, "label": "Unspecified" if value == "__unspecified__" else value, "color": colors[value], "count": count} for value, count in sorted(counts.items())]
    # The fixed palette includes the explicit missing-value class even when
    # absent in a future snapshot. Every possible category pair is tested.
    trace = [ColorAccessibilityGate().evaluate(list(pair)).to_dict() for pair in combinations(colors.values(), 2)]
    if not all(g["passed"] for g in trace):
        raise ValueError("Open-space categorical palette failed G5")
    entry = read_data("manifest")["files"]["parks.geojson"]
    payload = {"dataset_sha256": entry["sha256"], "dataset_version_id": entry["version_id"], "field": "FEATURE_CLASS", "categories": categories, "validation": {"color": trace[0], "trace": trace, "scope": "G5 checks every pair in the fixed FEATURE_CLASS palette and black text on white. Opaque categorical fill only; basemap contrast and overlap are not certified."}}
    payload["plan_id"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return payload


def _snap_roundtrip_breaks(breaks, values):
    """Remove floating-point log/exp roundtrip drift at observed values.

    An endpoint such as 13786.959999999988 must still contain 13786.96.
    Snap only within machine-scale tolerance, then submit to G2 again.
    """
    out = []
    for boundary in breaks:
        nearest = float(values[np.argmin(np.abs(values - boundary))])
        out.append(nearest if np.isclose(nearest, boundary, rtol=1e-12, atol=1e-9) else float(boundary))
    return sorted(set(out))


@lru_cache(maxsize=48)
def _plan(metric: str, palette: str, method: str):
    features = read_data("counties")["features"]
    values = np.array([f["properties"][metric] for f in features], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Dataset contains missing or invalid values")
    proposed = "jenks" if method == "auto" else method
    if proposed == "jenks":
        breaks = [float(x) for x in jenkspy.jenks_breaks(values, n_classes=5)]
    elif proposed == "quantile":
        breaks = [float(x) for x in np.percentile(values, [0, 20, 40, 60, 80, 100])]
    else:
        breaks = [float(x) for x in np.linspace(values.min(), values.max(), 6)]
    breaks = sorted(set(breaks))
    trace = []
    for _ in range(4):
        result = ClassificationDiagnosticEngine(random_state=0).evaluate(values, proposed, breaks)
        gate = adapt_gate2(result)
        trace.append(gate.to_dict())
        if gate.passed:
            break
        if not result.prescribed_breaks or result.prescribed_method == "manual_review":
            raise ValueError("Classification needs manual review")
        proposed = result.prescribed_method
        breaks = _snap_roundtrip_breaks(result.prescribed_breaks, values)
    if not gate.passed:
        raise ValueError("Classification did not converge")
    count = len(breaks) - 1
    ramps = {
        "forest": ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"],
        "ocean": ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"],
        "violet": ["#f2f0f7", "#cbc9e2", "#9e9ac8", "#756bb1", "#54278f"],
        "sunset": ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"],
    }
    rgb = np.array([[int(c[i:i+2], 16) for i in (1, 3, 5)] for c in ramps[palette]])
    sampled = np.array([np.interp(np.linspace(0, 4, count), np.arange(5), rgb[:, channel]) for channel in range(3)]).T
    colors = ["#" + "".join(f"{round(v):02x}" for v in row) for row in sampled]
    color_gate = ColorAccessibilityGate().evaluate(colors, variable_names=[metric])
    trace.append(color_gate.to_dict())
    adjusted = False
    if not color_gate.passed:
        colors = color_gate.prescription.params["palette"]
        color_gate = ColorAccessibilityGate().evaluate(colors, variable_names=[metric])
        trace.append(color_gate.to_dict())
        adjusted = True
    if not color_gate.passed or len(colors) != count:
        raise ValueError("The palette cannot safely represent the prescribed classes")
    legend = [{"min": float(breaks[i]), "max": float(breaks[i + 1]), "color": colors[i], "inclusive_min": i == 0} for i in range(count)]
    ranked = sorted((f["properties"] for f in features), key=lambda p: p[metric], reverse=True)
    payload = {
        "dataset_sha256": read_data("manifest")["files"]["counties.geojson"]["sha256"],
        "dataset_version_id": read_data("manifest")["files"]["counties.geojson"]["version_id"],
        "metric": metric, "title": METRICS[metric]["name"], "unit": METRICS[metric]["unit"],
        "requested_method": method, "method": proposed, "requested_palette": palette,
        "palette_adjusted": adjusted, "breaks": breaks, "colors": colors, "legend": legend,
        "summary": {"min": float(values.min()), "max": float(values.max()), "top_county": ranked[0]["name"], "count": len(values)},
        "validation": {"classification": gate.to_dict(), "color": color_gate.to_dict(), "trace": trace,
            "scope": "G2 classification and G5 opaque palette only. CRS, spatial structure, projection distortion, and publication completeness gates are not run for this web preview.",
            "display_note": "Web Mercator (EPSG:3857) for exploration. Opacity and basemap compositing are not covered by the palette check."},
        "source": "U.S. Census Bureau, 2019–2023 ACS 5-year estimates; NJOGIS county boundaries.",
    }
    payload["plan_id"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return payload


def plan(request: MapRequest):
    return _plan(request.metric, request.palette, request.method)


def guided_intent(message: str) -> Intent:
    text = message.strip().lower()
    unsupported = r"\b(flood|transit|crime|school|hospital|weather|buffer|correlation|bivariate|compare|within|above|below|greater|less than|poverty|unemployment|tract|municipalit|202[4-9]|2020|2010)\b"
    if re.search(unsupported, text) or re.search(r"[<>]", text):
        return Intent(action="unsupported")
    intent = Intent()
    county_text = text
    for feature in read_data("counties")["features"]:
        name = feature["properties"]["name"]
        # "Ocean" alone is a palette; "Ocean County" is a location.
        pattern = r"\b" + re.escape(name.lower()) + (r" county\b" if name == "Ocean" else r"\b")
        if re.search(pattern, text):
            intent.county = name
            county_text = re.sub(pattern, "", county_text)
            break
    if re.search(r"\b(income|wealth|richest|poorest|earnings)\b", text) and re.search(r"\b(density|population|people|populous)\b", text):
        return Intent(action="unsupported")
    # Guided mode is intentionally a finite command vocabulary. Unknown
    # locations or unsupported operations must not produce a plausible
    # statewide substitute merely because a metric keyword was present.
    allowed = set("show map add hide remove without turn on off park parks greenspace income household median wealth richest poorest earnings population total people populous density dense densest crowded make the it this that my a an in of for with and across to by use set change color colors palette green forest blue ocean purple violet orange sunset red quantile quantiles jenks natural breaks equal interval automatic reset statewide all counties entire state new jersey nj county focus zoom highest most lowest least please me can you as style".split())
    allowed.update("locations location points point polygons polygon open space owned which what where do does live living is are has have how much view want would plot i like".split())
    if any(word not in allowed for word in re.findall(r"[a-z]+|[0-9]+", county_text)):
        return Intent(action="unsupported")
    if re.search(r"\b(income|wealth|richest|poorest|earnings)\b", text):
        intent.metric = "income"
    elif re.search(r"\b(density|dense|densest|crowded)\b", text):
        intent.metric = "density"
    elif re.search(r"\b(population|populous|people)\b", text):
        intent.metric = "population"
    if re.search(r"\b(parks?|greenspace|open space)\b", text):
        intent.parks = not bool(re.search(r"\b(hide|remove|without)\b", text))
    for pattern, name in [(r"green|forest", "forest"), (r"blue|ocean", "ocean"), (r"purple|violet", "violet"), (r"orange|sunset|red", "sunset")]:
        if re.search(r"\b(" + pattern + r")\b", county_text):
            intent.palette = name
    for word, name in [("quantile", "quantile"), ("jenks", "jenks"), ("natural breaks", "jenks"), ("equal interval", "equal_interval"), ("automatic", "auto")]:
        if word in text:
            intent.method = name
    intent.statewide = bool(re.search(r"\b(reset|statewide|all counties|entire state|new jersey|\bnj)\b", text)) and not intent.county
    if not any([intent.metric, intent.palette, intent.method, intent.parks is not None, intent.county, intent.statewide]):
        intent.action = "unsupported"
    return intent


class WebIntentClient(NvidiaLLM):
    """Reuse the existing provider transport with a strict web command schema.

    Unlike the CLI client's heuristic transport fallback, web failures are
    surfaced explicitly so unavailable intent is never silently substituted.
    """

    DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"

    def __init__(self, model=None, api_key=None, *, timeout=60, max_retries=0):
        super().__init__(model=model or self.DEFAULT_MODEL, api_key=api_key, timeout=timeout, max_retries=max_retries)
        self.version = "web-intent-v1"

    def _chat(self, system: str, user: str) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.0, "max_tokens": 512, "stream": True,
        }
        if "nemotron" in self.model:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        return self._stream_once(body)

    def parse(self, message: str, current: MapRequest) -> tuple[Intent, dict]:
        context = SemanticContext(
            dataset_schemas=[FieldSchema(name=k, dtype="float64", unit=v["unit"], description=v["description"]) for k, v in METRICS.items()],
            aoi=AreaOfInterest(id="nj", bbox_4326=(-75.6, 38.9, -73.8, 41.4), feature_count=21, description="New Jersey counties"),
        )
        system = (
            "Parse a New Jersey web map command. Return ONLY JSON: action (map, style, focus, unsupported), "
            "metric (density, population, income or null), palette (forest, ocean, violet, sunset or null), "
            "method (auto, quantile, jenks, equal_interval or null), parks (boolean or null), county (name or null), statewide (boolean). "
            "Omit unchanged settings or use null. Supports one county demographic fill and optional NJDEP state-owned open-space polygons. "
            "County focus only zooms: it never filters statistics. Data is ACS 2019–2023 and a pinned NJDEP layer 67 snapshot. "
            "For unavailable datasets, different vintages, comparison/bivariate maps, numeric filters, spatial analysis, or any "
            "request you cannot fully satisfy, return action unsupported. Do not calculate numbers, invent data or emit code. "
            "Current map: " + current.model_dump_json() + ". Available metadata: " + json.dumps(context.to_dict())
        )
        raw = self._chat(system, message)
        if raw.strip().startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        intent = Intent.model_validate_json(raw)
        record = self._record(context).to_dict()
        record["prompt_hash"] = hashlib.sha256((system + message).encode()).hexdigest()
        return intent, record


def chat(request: ChatRequest):
    if not request.message.strip():
        raise ValueError("Enter a map request")
    record = {"provider": "guided", "model": "deterministic commands"}
    if request.use_ai:
        if is_offline() or not get_key("NVIDIA_API_KEY", required=False):
            raise ValueError("AI is unavailable. Use guided mode or configure NVIDIA_API_KEY on the server.")
        try:
            intent, record = WebIntentClient(model=get_key("AUTOCARTO_WEB_MODEL", required=False), timeout=60, max_retries=0).parse(request.message, request.current)
        except Exception:
            raise ValueError("The AI provider could not resolve this request. Try again or switch to guided mode.") from None
    else:
        intent = guided_intent(request.message)
    county_names = [f["properties"]["name"] for f in read_data("counties")["features"]]
    if intent.county:
        intent.county = next((c for c in county_names if c.lower() == intent.county.lower().removesuffix(" county")), None)
        if intent.county is None:
            intent.action = "unsupported"
    if intent.action == "unsupported":
        return {"applied": False, "message": "I can map NJ county population, density, and income; show state-owned open space; change palettes; or focus on a county. This request goes beyond the loaded data or supported commands. Try “Show household income with parks.”", "provider": record}
    options = request.current.model_dump()
    for key in ("metric", "palette", "method"):
        if getattr(intent, key) is not None:
            options[key] = getattr(intent, key)
    result = plan(MapRequest(**options))
    parts = [f"Mapped {result['title'].lower()} across New Jersey's 21 counties."]
    if intent.parks is not None:
        parts.append(f"{'Added' if intent.parks else 'Hid'} the NJDEP state-owned open-space polygons.")
    if intent.county:
        parts.append(f"Zoomed to {intent.county} County; the classification still uses all 21 counties.")
    if intent.statewide:
        parts.append("Showing the statewide view.")
    if result["palette_adjusted"]:
        parts.append("Adjusted the requested palette to meet the color accessibility gate.")
    if any(word in request.message.lower() for word in ["highest", "most", "richest", "densest"]):
        parts.append(f"{result['summary']['top_county']} County has the highest value in this snapshot ({result['summary']['max']:,.0f} {result['unit']}).")
    if any(word in request.message.lower() for word in ["lowest", "least", "poorest"]):
        lowest = min(read_data("counties")["features"], key=lambda f: f["properties"][options["metric"]])["properties"]
        parts.append(f"{lowest['name']} County has the lowest value in this snapshot ({lowest[options['metric']]:,.0f} {result['unit']}).")
    return {"applied": True, "message": " ".join(parts), "map": result, "settings": options, "parks": request.parks if intent.parks is None else intent.parks, "county": intent.county, "statewide": intent.statewide, "provider": record}
