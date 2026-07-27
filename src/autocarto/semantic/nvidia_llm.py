"""Tier 1 — real open-source LLM client via NVIDIA's OpenAI-compatible API.

Implements the same ``LLMClient`` interface as ``MockLLM``, backed by an
actual open-weights model (default ``meta/llama-3.1-70b-instruct``) served
at ``https://integrate.api.nvidia.com/v1``. No new dependency — talks to
the HTTP endpoint with the stdlib, streaming the response so slow large
models don't idle-timeout the socket.

Where the real LLM actually does work — and where it deliberately doesn't:

  * **Intent parsing (genuine LLM discretion).** On a fresh proposal (no
    prescriptions yet) the model reads the user's free-text request plus
    the *names/roles/units* of the available variables and decides the
    map type and which variables to use. This is the one step with real
    semantic latitude, and it is exactly the "reasons over concepts, never
    data values" role the architecture assigns Tier 1 — the model never
    sees a single data value (SemanticContext guarantees this by type).

  * **Mandate iterations (no discretion — deterministic transcription).**
    After a gate REJECT, the prescription is an *exact* mandate (specific
    breaks, a specific EPSG, a specific palette). The architecture's whole
    thesis is that the LLM has no say over these numbers, so this client
    does NOT spend a second API call echoing them back (which would add
    latency, cost, and a real risk of the model mis-transcribing a float).
    It applies the mandate deterministically — the faithful implementation
    of "reduce the LLM to a code-assembler," and identical in effect to
    MockLLM's transcription branch.

Determinism note: temperature is 0, but real LLM inference is not
bit-reproducible across calls (server-side nondeterminism). What is
reproducible is the *gate decisions* — the deterministic Tier-2 layer —
for a given proposal; that is the project's reproducibility claim, not the
raw model tokens. The trace records the provider, model id, and prompt
hash so a run is auditable regardless.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from autocarto.contracts import MapProposal, SemanticContext
from autocarto.env import get_key
from autocarto.semantic.llm_client import LLMCallRecord, LLMClient

_VALID_MAP_TYPES = {"choropleth", "bivariate", "proportional_symbol"}
_VALID_PURPOSES = {"area_comparison", "shape", "distance"}


class NvidiaLLM(LLMClient):
    """Real open-source LLM behind NVIDIA's OpenAI-compatible endpoint."""

    provider = "nvidia"
    DEFAULT_MODEL = "meta/llama-3.1-70b-instruct"
    BASE_URL = "https://integrate.api.nvidia.com/v1"

    DEFAULT_PALETTE: List[str] = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]

    _SYSTEM_PROMPT = (
        "You are the intent parser of a cartographic system. You reason ONLY about "
        "what KIND of map the user wants and WHICH of the available variables to use. "
        "You never see the data values themselves and you do NOT choose classification "
        "breaks, colors, or projections — a deterministic engine decides all of those.\n\n"
        "Respond with ONLY a compact JSON object (no prose, no markdown fences) with keys:\n"
        '  "map_type": one of ["choropleth", "bivariate", "proportional_symbol"]\n'
        '  "variables": a list of variable names, each EXACTLY as spelled in the '
        "AVAILABLE VARIABLES list below (do not invent or rename)\n"
        '  "map_purpose": one of ["area_comparison", "shape", "distance"]\n\n'
        "RULES:\n"
        "- A request that RELATES, COMPARES, or ASSOCIATES two variables -> map_type "
        '"bivariate" with both variables.\n'
        "- A request that maps ONE quantity shaded by area -> \"choropleth\".\n"
        "- A request that maps ONE quantity as sized points/circles -> \"proportional_symbol\".\n"
        "- Choose the SMALLEST set of variables that answers the request.\n"
        '- Default map_purpose to "area_comparison" unless the request is clearly about '
        "shape or distance."
    )

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        *,
        timeout: int = 180,
        max_retries: int = 1,
        default_palette: Optional[List[str]] = None,
    ) -> None:
        self.model = model
        self.version = "intent-v1"  # prompt-template version (for trace provenance)
        self.temperature = 0.0
        self._api_key = api_key or get_key("NVIDIA_API_KEY")
        self._timeout = timeout
        self._max_retries = max_retries
        self.default_palette = list(default_palette) if default_palette else list(self.DEFAULT_PALETTE)
        # Intent parsed on the most recent fresh proposal, reused across that
        # run's mandate iterations (refreshed whenever prescriptions is empty).
        self._last_intent: Optional[Dict[str, Any]] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def propose(self, context: SemanticContext, prompt: str) -> Tuple[MapProposal, LLMCallRecord]:
        record = self._record(context)
        available = [s.name for s in context.dataset_schemas]
        roles = {s.name: s.role for s in context.dataset_schemas if s.role}

        if not context.prescriptions:
            # Fresh proposal: genuine intent parse via the real model.
            intent = self._parse_intent(context, prompt, available)
            self._last_intent = intent
        else:
            # Mandate iteration: reuse the run's parsed intent, no API call.
            intent = self._last_intent or self._heuristic_intent(available)

        map_type = intent["map_type"]
        variables = intent["variables"]
        map_purpose = intent["map_purpose"]

        method: Optional[str] = "jenks"          # naive first-pass method; gates prescribe the real one
        breaks: Optional[List[float]] = None
        projection_epsg: Optional[int] = None
        palette = list(self.default_palette)

        if context.prescriptions:
            latest = context.prescriptions[-1]
            method = latest.method
            if latest.params.get("breaks"):
                breaks = list(latest.params["breaks"])
            if latest.params.get("target_epsg"):
                projection_epsg = int(latest.params["target_epsg"])
            if latest.params.get("palette"):
                palette = list(latest.params["palette"])

        proposal = MapProposal(
            map_type=map_type,
            variables=variables,
            variable_roles={v: roles[v] for v in variables if v in roles},
            classification_method=method,
            classification_breaks=breaks,
            projection_epsg=projection_epsg,
            palette=palette,
            diverging_palette=(map_type == "bivariate"),
            template_id=f"{map_type}_v1",
            map_purpose=map_purpose,
            iteration=len(context.prescriptions),
        )
        return proposal, record

    # ── Intent parsing ────────────────────────────────────────────────────────

    def _parse_intent(self, context: SemanticContext, prompt: str, available: List[str]) -> Dict[str, Any]:
        """Call the real model to infer map_type/variables/purpose, then
        validate hard against the available schema. Any failure (network,
        malformed JSON, invalid values) falls back to the heuristic — the
        gates validate the proposal regardless, so a bad parse degrades
        gracefully instead of crashing the run."""
        schema_lines = []
        for s in context.dataset_schemas:
            bits = [s.name]
            if s.role:
                bits.append(f"role={s.role}")
            if s.unit:
                bits.append(f"unit={s.unit}")
            schema_lines.append("  - " + ", ".join(bits))
        user_msg = (
            f"USER REQUEST:\n{prompt}\n\n"
            f"AVAILABLE VARIABLES (use names exactly):\n" + "\n".join(schema_lines) +
            f"\n\nAREA OF INTEREST: {context.aoi.description or context.aoi.id}"
        )
        try:
            content = self._chat(self._SYSTEM_PROMPT, user_msg)
            parsed = _extract_json(content)
            return self._validate_intent(parsed, available)
        except Exception:
            return self._heuristic_intent(available)

    def _validate_intent(self, parsed: Dict[str, Any], available: List[str]) -> Dict[str, Any]:
        map_type = parsed.get("map_type")
        if map_type not in _VALID_MAP_TYPES:
            map_type = None

        raw_vars = parsed.get("variables") or []
        if not isinstance(raw_vars, list):
            raw_vars = []
        # Keep only variables that actually exist in the schema (exact match,
        # then case-insensitive). The model must not invent variable names —
        # the orchestrator indexes real data by these.
        avail_lower = {a.lower(): a for a in available}
        variables: List[str] = []
        for v in raw_vars:
            if not isinstance(v, str):
                continue
            if v in available:
                variables.append(v)
            elif v.lower() in avail_lower:
                variables.append(avail_lower[v.lower()])
        # de-dup, preserve order
        seen: set = set()
        variables = [v for v in variables if not (v in seen or seen.add(v))]

        if not variables:
            variables = available[:2] if len(available) >= 2 else available[:1]
        if map_type is None:
            map_type = "bivariate" if len(variables) >= 2 else "choropleth"
        # A bivariate map needs exactly two variables; a univariate map one.
        if map_type == "bivariate" and len(variables) < 2:
            map_type = "choropleth"
        if map_type != "bivariate":
            variables = variables[:1]
        else:
            variables = variables[:2]

        purpose = parsed.get("map_purpose")
        if purpose not in _VALID_PURPOSES:
            purpose = "area_comparison"

        return {"map_type": map_type, "variables": variables, "map_purpose": purpose}

    @staticmethod
    def _heuristic_intent(available: List[str]) -> Dict[str, Any]:
        if len(available) >= 2:
            return {"map_type": "bivariate", "variables": available[:2], "map_purpose": "area_comparison"}
        return {"map_type": "choropleth", "variables": available[:1], "map_purpose": "area_comparison"}

    # ── HTTP (streaming) ──────────────────────────────────────────────────────

    def _chat(self, system: str, user: str) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": 200,
            "stream": True,
        }
        last_err: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._stream_once(body)
            except Exception as exc:  # noqa: BLE001 — retry on any transport/parse error
                last_err = exc
                if attempt < self._max_retries:
                    time.sleep(1.0)
        raise RuntimeError(f"NVIDIA chat failed after {self._max_retries + 1} attempts: {last_err}")

    def _stream_once(self, body: Dict[str, Any]) -> str:
        req = urllib.request.Request(
            f"{self.BASE_URL}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        chunks: List[str] = []
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue  # keepalive / partial line — skip
                choices = obj.get("choices")
                if not choices:
                    continue  # usage-only or empty chunk
                delta = choices[0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    chunks.append(piece)
        return "".join(chunks)


def _extract_json(text: str) -> Dict[str, Any]:
    """Pull the first JSON object out of a model response that may be wrapped
    in prose or ```json fences."""
    if not text:
        raise ValueError("empty response")
    # strip common markdown fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    # otherwise take the first balanced {...} span
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in response")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unbalanced JSON object in response")
