"""Constrained code generator — Blueprint §5.

The key security+correctness decision in the whole architecture: the LLM
fills declarative *slots* in audited, per-map-type render templates. It
never writes free-form Python. The sandbox then executes template code
plus already-gate-validated constants — never LLM-authored logic.

This collapses most of the sandbox's attack surface (Manual §10 — a
template the LLM cannot alter has no code-injection surface beyond the
slot values, which are typed and, per `RenderPlan.validate()`, provably
not of ``FREE_LLM`` provenance) and makes Gate 6's completeness manifest
trivial: each template *declares* which manifest elements it always
supplies, so the manifest does not need to be inferred from the rendered
figure after the fact. All three templates are written to satisfy Gate 6's
full required-element set for their map type (config.py
``required_elements_*``) — verified in tests/test_codegen.py by actually
running each template's output through ``CompletenessGate``.

Templates are `string.Template` bodies (``$slot`` substitution, not
``str.format``) specifically because the template bodies themselves
contain literal ``{`` / ``}`` in dict literals and f-strings — ``.format()``
would require escaping every one of those, which is exactly the kind of
fragile string surgery this design replaces (see sandbox.py TD-9 fix for
the same lesson applied to stylesheet injection).
"""

from __future__ import annotations

from string import Template
from typing import Any, Dict, FrozenSet, Tuple

from autocarto.contracts import MapProposal, RenderPlan
from autocarto.execution.gates.gate6_completeness import RenderManifest

# ── Shared scale-bar snippet ─────────────────────────────────────────────────
# A real scale bar computed from the GeoDataFrame's own extent in whatever
# CRS it is currently in (not a decorative fixed-length bar) -- deliberately
# not the ``matplotlib-scalebar`` package, which is not a project dependency.
_SCALE_BAR_SNIPPET = '''\
_xmin, _ymin, _xmax, _ymax = gdf.total_bounds
_bar_len = (_xmax - _xmin) * 0.2
_bar_x0 = _xmin + (_xmax - _xmin) * 0.05
_bar_y0 = _ymin + (_ymax - _ymin) * 0.05
_unit = "m" if (gdf.crs is not None and gdf.crs.is_projected) else "deg"
ax.plot([_bar_x0, _bar_x0 + _bar_len], [_bar_y0, _bar_y0],
        color="black", linewidth=2, solid_capstyle="butt")
ax.text(_bar_x0 + _bar_len / 2, _bar_y0, f"{_bar_len:.0f} {_unit}",
        ha="center", va="bottom", fontsize=6)
'''

_CRS_CAPTION_SNIPPET = '''\
if _crs_note:
    fig.text(0.99, 0.01, _crs_note, ha="right", fontsize=6, color="0.4")
'''

# ── Audited templates ─────────────────────────────────────────────────────────
# Each entry: (Template, frozenset of RenderManifest elements it guarantees).
# "Guarantees" means: if this template is used as-is (slots filled, not
# edited), the corresponding RenderManifest field is always populated —
# Gate 6 can trust it without inspecting the rendered artifact.

_CHOROPLETH_TEMPLATE = Template('''\
# AUTOCARTO GENERATED -- choropleth (template_id=choropleth_v1)
# Slots filled from a gate-validated RenderPlan; no LLM-authored logic below.
# Classification uses an explicit BoundaryNorm over the prescribed breaks
# (not GeoDataFrame.plot(scheme=...), which needs the optional
# 'mapclassify' package) -- same pattern as figures/gen_results_panel.py.
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.cm import ScalarMappable

_breaks = $breaks
_palette = $palette
_title = $title
_crs_note = $crs_note

_n_classes = len(_breaks) - 1
_cmap = ListedColormap(_palette) if isinstance(_palette, list) else plt.get_cmap(_palette, _n_classes)
_norm = BoundaryNorm(_breaks, _cmap.N)

_classification_note = $classification_note

fig, ax = plt.subplots(figsize=(10, 8))
gdf.plot(column=variable_column, ax=ax, cmap=_cmap, norm=_norm, edgecolor="white", linewidth=0.2)
_sm = ScalarMappable(cmap=_cmap, norm=_norm)
_sm.set_array([])
fig.colorbar(_sm, ax=ax, shrink=0.6, label=_title)
ax.set_title(_title)
ax.set_axis_off()
if _classification_note:
    ax.text(
        0.02, 0.98, _classification_note, transform=ax.transAxes,
        fontsize=7, va="top", ha="left",
        bbox={"fc": "white", "ec": "0.7", "alpha": 0.9},
    )
''' + _SCALE_BAR_SNIPPET + _CRS_CAPTION_SNIPPET + '''\
fig.text(0.5, 0.01, $citation, ha="center", fontsize=6, color="0.4")
''')

_BIVARIATE_TEMPLATE = Template('''\
# AUTOCARTO GENERATED -- bivariate choropleth (template_id=bivariate_v1)
import matplotlib.pyplot as plt

_title = $title
_correlation_note = $correlation_note
_classification_note = $classification_note
_crs_note = $crs_note

fig, ax = plt.subplots(figsize=(10, 8))
gdf.plot(ax=ax, color=bivariate_colors, edgecolor="white", linewidth=0.15)
ax.set_title(_title)
ax.set_axis_off()
ax.text(
    0.02, 0.02, _correlation_note, transform=ax.transAxes,
    fontsize=7, va="bottom", ha="left",
    bbox={"fc": "white", "ec": "0.7", "alpha": 0.9},
)
if _classification_note:
    ax.text(
        0.02, 0.98, _classification_note, transform=ax.transAxes,
        fontsize=7, va="top", ha="left",
        bbox={"fc": "white", "ec": "0.7", "alpha": 0.9},
    )
''' + _SCALE_BAR_SNIPPET + _CRS_CAPTION_SNIPPET + '''\
fig.text(0.5, 0.01, $citation, ha="center", fontsize=6, color="0.4")
''')

_PROPORTIONAL_SYMBOL_TEMPLATE = Template('''\
# AUTOCARTO GENERATED -- proportional symbol (template_id=proportional_symbol_v1)
import matplotlib.pyplot as plt

_title = $title
_crs_note = $crs_note

fig, ax = plt.subplots(figsize=(10, 8))
gdf.boundary.plot(ax=ax, color="0.75", linewidth=0.4)
centroids = gdf.geometry.centroid
_sizes = 20 + 400 * (values - values.min()) / max(1e-9, (values.max() - values.min()))
_scatter = ax.scatter(centroids.x, centroids.y, s=_sizes, alpha=0.65, color="#2166ac",
                      edgecolor="white", linewidth=0.4)
_handles, _labels = _scatter.legend_elements(prop="sizes", num=3, func=lambda s: (s - 20) / 400 * (values.max() - values.min()) + values.min())
ax.legend(_handles, _labels, title=_title, loc="lower left", fontsize=6, title_fontsize=7, framealpha=0.9)
ax.set_title(_title)
ax.set_axis_off()
''' + _SCALE_BAR_SNIPPET + _CRS_CAPTION_SNIPPET + '''\
fig.text(0.5, 0.01, $citation, ha="center", fontsize=6, color="0.4")
''')

TEMPLATES: Dict[str, Tuple[Template, FrozenSet[str]]] = {
    "choropleth_v1": (
        _CHOROPLETH_TEMPLATE,
        frozenset({"title", "legend", "citation", "scale_or_graticule", "crs_note", "classification_note"}),
    ),
    "bivariate_v1": (
        _BIVARIATE_TEMPLATE,
        frozenset({"title", "bivariate_legend", "citation", "correlation_statistic",
                  "scale_or_graticule", "crs_note", "classification_note"}),
    ),
    "proportional_symbol_v1": (
        _PROPORTIONAL_SYMBOL_TEMPLATE,
        frozenset({"title", "legend", "citation", "scale_or_graticule", "crs_note"}),
    ),
}


def _classification_note(template_id: str, proposal: MapProposal, render_plan: RenderPlan) -> Any:
    if template_id == "choropleth_v1" and isinstance(render_plan.breaks.value, list):
        return f"{proposal.classification_method}, {len(render_plan.breaks.value) - 1} classes"
    if template_id == "bivariate_v1":
        return "Tertile classification per variable (3x3 bivariate scheme)"
    return None


def _py_literal(value: Any) -> str:
    """Render a Python value as source text via repr — safe because the
    value always originates from a ProvenancedValue already validated as
    GATE_PRESCRIBED or TEMPLATE_DEFAULT (never a raw LLM string)."""
    return repr(value)


def generate(
    proposal: MapProposal,
    render_plan: RenderPlan,
    *,
    citation: str,
    crs_note: str = "",
    correlation_note: str = "",
) -> Tuple[str, RenderManifest]:
    """Fill an audited template's slots and return (code, manifest).

    Raises `AuthorityViolation` (via `render_plan.validate()`) if any
    render constant has ``FREE_LLM`` provenance — this is the last
    checkpoint before code text exists at all.
    """
    render_plan.validate()

    template_id = render_plan.template_id.value
    entry = TEMPLATES.get(template_id)
    if entry is None:
        raise ValueError(f"Unknown template_id {template_id!r}; must be one of {sorted(TEMPLATES)}")
    template, guaranteed_elements = entry

    title = f"{', '.join(proposal.variables)} — {proposal.map_type.replace('_', ' ').title()}"
    classification_note = _classification_note(template_id, proposal, render_plan)

    if template_id == "choropleth_v1":
        code = template.substitute(
            breaks=_py_literal(render_plan.breaks.value),
            palette=_py_literal(render_plan.palette.value),
            title=_py_literal(title),
            citation=_py_literal(citation),
            crs_note=_py_literal(crs_note),
            classification_note=_py_literal(classification_note or ""),
        )
    elif template_id == "bivariate_v1":
        code = template.substitute(
            title=_py_literal(title),
            citation=_py_literal(citation),
            correlation_note=_py_literal(correlation_note),
            crs_note=_py_literal(crs_note),
            classification_note=_py_literal(classification_note or ""),
        )
    else:  # proportional_symbol_v1
        code = template.substitute(
            title=_py_literal(title),
            citation=_py_literal(citation),
            crs_note=_py_literal(crs_note),
        )

    # Every field here is gated on "is this in the template's own declared
    # guarantee," including classification_note -- an earlier version left
    # that one field unconditional (always computed a value regardless of
    # guaranteed_elements), which made Gate 6 believe a choropleth's
    # classification note was present when the template never actually drew
    # it. A real user caught this by comparing a rendered map against its
    # own trace; see tests/test_codegen.py's guaranteed-vs-rendered checks.
    manifest = RenderManifest(
        title=title if "title" in guaranteed_elements else None,
        legend_present="legend" in guaranteed_elements,
        bivariate_legend_present="bivariate_legend" in guaranteed_elements,
        scale_bar_present="scale_or_graticule" in guaranteed_elements,
        data_citation=citation if "citation" in guaranteed_elements else None,
        crs_note=(crs_note or None) if "crs_note" in guaranteed_elements else None,
        classification_note=(
            classification_note if "classification_note" in guaranteed_elements else None
        ),
        correlation_statistic_shown=(
            "correlation_statistic" in guaranteed_elements and bool(correlation_note)
        ),
    )
    return code, manifest
