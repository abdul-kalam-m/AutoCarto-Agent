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
       adopts each field (classification method/breaks, projection,
       palette) from whichever accumulated prescription actually supplies
       it — "the LLM's remaining job is transcription of the mandated
       method" (poster copy §2). This is what makes bounded (<=3
       iteration) convergence plausible even with a weak LLM.

       PATCH (found 2026-07-27): originally read every field from only
       ``context.prescriptions[-1]`` (the single most recent rejection).
       That silently broke as soon as two gates could REJECT on the same
       iteration (e.g. Gate 2 on missing breaks and Gate 5 on an unsafe/
       miscoded palette at once, both real once Gate 5 gained a check that
       can fire on the very first, palette-naive proposal): whichever gate
       happened to run last (GATE_ORDER) would have its prescription
       "shadow" the other's in ``[-1]``, so e.g. Gate 5's palette fix would
       silently discard Gate 2's breaks fix, and vice versa -- exactly the
       gap ``GateSuiteResult.consolidated_mandate()`` exists to prevent
       (its own docstring: "collect every rejection's prescription...
       rather than round-tripping gate-by-gate"). Fixed by scanning every
       accumulated prescription and taking each field from whichever one
       (most recently) actually supplies it, independently per field.
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
        # Trim to the arity the map type actually encodes. NvidiaLLM's intent
        # validator already does this; MockLLM did not, which was invisible
        # while every dataset had exactly two variables. With three, it
        # proposed a "bivariate" map naming all three while Gate 3b and the
        # renderer only ever consume variables[0] and variables[1] -- so the
        # title and the citation footer would both claim a variable the map
        # does not encode.
        variables = variables[:2] if map_type == "bivariate" else variables[:1]

        method: Optional[str] = "jenks"
        breaks: Optional[List[float]] = None
        projection_epsg: Optional[int] = None
        palette = list(self.default_palette)

        # Each field is sourced independently from whichever accumulated
        # prescription (most recently) actually supplies it -- not just
        # prescriptions[-1] -- so two gates rejecting on the same iteration
        # (e.g. G2 on missing breaks, G5 on palette) both get addressed
        # instead of the later one in GATE_ORDER silently shadowing the
        # earlier one's fix. See the PATCH note in the class docstring.
        for p in context.prescriptions:
            prescribed_breaks = p.params.get("breaks")
            if prescribed_breaks:
                method = p.method
                breaks = list(prescribed_breaks)
            prescribed_epsg = p.params.get("target_epsg")
            if prescribed_epsg:
                projection_epsg = int(prescribed_epsg)
            prescribed_palette = p.params.get("palette")
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
