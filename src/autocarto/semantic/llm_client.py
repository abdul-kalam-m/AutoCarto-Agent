"""Tier 1 LLM client — provider-agnostic interface + MockLLM (Blueprint §5).

``LLMClient`` is the interface every backend implements: structured output,
temperature 0, and a call record of ``{provider, model, version,
prompt_hash}`` for the trace (Blueprint §5 / abstract claim C11). Its
``propose`` method's *only* input besides the free-text prompt is a
``SemanticContext`` — schemas, diagnoses, prescriptions, never data — so
the authority boundary is enforced by the type signature itself, not by
what a particular implementation chooses to do with its input.

This module ships the interface plus ``MockLLM``, a deterministic
rule-based stand-in. That is deliberate, not a placeholder: the P2
acceptance criterion (Manual §11) is that the orchestrator works fully
offline against a mock before any real API key exists, and a real
provider client is additive later behind the same interface — building it
is not required to prove the orchestrator loop itself works.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from autocarto.contracts import MapProposal, SemanticContext


@dataclass(frozen=True)
class LLMCallRecord:
    """Trace payload for one LLM call — Blueprint §5."""
    provider: str
    model: str
    version: str
    prompt_hash: str
    temperature: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "version": self.version,
            "prompt_hash": self.prompt_hash,
            "temperature": self.temperature,
        }


class LLMClient(ABC):
    """Provider-agnostic interface every Tier-1 backend implements."""

    provider: str
    model: str
    version: str
    temperature: float = 0.0

    @abstractmethod
    def propose(self, context: SemanticContext, prompt: str) -> Tuple[MapProposal, LLMCallRecord]:
        """Produce a MapProposal from a SemanticContext and the user's prompt.

        Implementations receive *only* ``context`` (schemas/diagnoses/
        prescriptions, per SemanticContext's construction-time guarantee)
        and the free-text ``prompt`` — never a data array, Series, or
        GeoDataFrame. There is no parameter through which raw data could
        pass even if an implementation wanted to leak it.
        """
        raise NotImplementedError

    def _record(self, context: SemanticContext) -> LLMCallRecord:
        return LLMCallRecord(
            provider=self.provider,
            model=self.model,
            version=self.version,
            prompt_hash=context.prompt_hash(),
            temperature=self.temperature,
        )


class MockLLM(LLMClient):
    """Deterministic, rule-based stand-in for a real LLM client.

    Models the two behaviors the architecture's thesis depends on:

    1. **Fresh proposal, no prescription yet:** names a plausible method
       ("jenks") with no computed break values — exactly what a
       temperature-0 model asked to classify data *it cannot see* can
       honestly produce. It is this gap (a method name with no real
       breaks) that gives Gate 2 something to evaluate and, typically,
       reject on the first pass.
    2. **A prescription is present in the context (post-rejection):**
       adopts the most recent prescription's method/breaks/projection/
       palette verbatim — "the LLM's remaining job is transcription of
       the mandated method" (poster copy §2). This is what makes bounded
       (<=3 iteration) convergence plausible even with a weak LLM.
    """

    provider = "mock"
    model = "deterministic-rule-based"
    version = "1.0"
    temperature = 0.0

    DEFAULT_PALETTE: List[str] = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]

    def __init__(self, default_map_type: str = "choropleth", default_palette: Optional[List[str]] = None):
        self.default_map_type = default_map_type
        self.default_palette = list(default_palette) if default_palette else list(self.DEFAULT_PALETTE)

    def propose(self, context: SemanticContext, prompt: str) -> Tuple[MapProposal, LLMCallRecord]:
        record = self._record(context)

        variables = [s.name for s in context.dataset_schemas]
        roles = {s.name: s.role for s in context.dataset_schemas if s.role}

        map_type = "bivariate" if len(variables) >= 2 else self.default_map_type

        method: Optional[str] = "jenks"
        breaks: Optional[List[float]] = None
        projection_epsg: Optional[int] = None
        palette = list(self.default_palette)

        if context.prescriptions:
            latest = context.prescriptions[-1]
            method = latest.method
            prescribed_breaks = latest.params.get("breaks")
            if prescribed_breaks:
                breaks = list(prescribed_breaks)
            prescribed_epsg = latest.params.get("target_epsg")
            if prescribed_epsg:
                projection_epsg = int(prescribed_epsg)
            prescribed_palette = latest.params.get("palette")
            if prescribed_palette:
                palette = list(prescribed_palette)

        proposal = MapProposal(
            map_type=map_type,
            variables=variables,
            variable_roles=roles,
            classification_method=method,
            classification_breaks=breaks,
            projection_epsg=projection_epsg,
            palette=palette,
            diverging_palette=(map_type == "bivariate"),
            template_id=f"{map_type}_v1",
            iteration=len(context.prescriptions),
        )
        return proposal, record
