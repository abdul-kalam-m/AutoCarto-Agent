#!/usr/bin/env python
"""Live demo: type a prompt, a real LLM plans the map, the gates fix it.

This is the unscripted counterpart to demo_for_video.py. Nothing here is a
narrated storyboard -- you pass a natural-language prompt, a real hosted
open-weights model parses it, the deterministic gates accept or reject what
it proposed, and a map is written. What you see is whatever actually
happens.

    python scripts/demo_live.py "Map population density across Atlanta"
    python scripts/demo_live.py "Show how income relates to asthma" --var income asthma
    python scripts/demo_live.py "Map median household income" --var income --open

Variables:
    income   real Census ACS B19013 median household income   (skew 1.13)
    asthma   real CDC PLACES CASTHMA adult prevalence         (skew 0.34)
    density  real ACS B01003 population / tract area          (skew 5.93)

`density` is the interesting one for a before/after comparison: it is a
genuinely heavy-tailed real variable, so a default equal-interval
classification puts ~97% of tracts in a single class. The other two are
only mildly skewed -- worth knowing before promising a dramatic failure on
camera.

Provenance note for `density`: population comes from the Census API at run
time (cached under output/demo_live/); the denominator is the area of each
tract polygon in the pinned TIGER snapshot, reprojected to EPSG:5070
(equal-area). That polygon area includes any water within the tract, so
this is tract-polygon density rather than strict land-area density. Fulton
and DeKalb are inland, so the difference is small -- but it is a real
caveat and is not a substitute for TIGER's ALAND field. This script is demo
tooling; it deliberately does not add a variable to the validated
`real_data.load_real_atlanta_dataset()` contract or to data/MANIFEST.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "output" / "demo_live"

VALID = ("income", "asthma", "density")
COLUMN = {
    "income": "median_household_income",
    "asthma": "asthma_prevalence",
    "density": "population_density",
}


def fetch_population(cache: Path) -> dict:
    """Total population per tract (ACS B01003), cached after first call."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    sys.path.insert(0, str(REPO / "src"))
    from autocarto.env import get_key

    key = get_key("CENSUS_API_KEY")
    url = (
        "https://api.census.gov/data/2022/acs/acs5?get=NAME,B01003_001E"
        "&for=tract:*&in=state:13&in=county:089,121&key=" + key
    )
    with urllib.request.urlopen(url, timeout=60) as resp:
        rows = json.load(resp)

    hdr, data = rows[0], rows[1:]
    pop = {}
    for row in data:
        rec = dict(zip(hdr, row))
        geoid = rec["state"] + rec["county"] + rec["tract"]
        try:
            pop[geoid] = float(rec["B01003_001E"])
        except (TypeError, ValueError):
            continue  # Census sentinel / missing -> drop, never impute

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(pop), encoding="utf-8")
    return pop


def build_dataset(which: list[str]):
    """A Dataset carrying exactly the requested real variables."""
    import numpy as np

    from autocarto.orchestrator import Dataset
    from autocarto.real_data import load_real_atlanta_dataset

    base_names = [COLUMN[w] for w in which if w in ("income", "asthma")]
    ds = load_real_atlanta_dataset(
        variables=base_names or ["median_household_income"]
    )

    if "density" not in which:
        return ds

    pop = fetch_population(OUT / "population_b01003.json")
    gdf = ds.gdf.copy()
    area_km2 = gdf.to_crs(epsg=5070).geometry.area / 1e6
    mapped = gdf["GEOID"].map(pop)

    keep = mapped.notna().to_numpy() & (area_km2 > 0).to_numpy()
    gdf = gdf.loc[keep].reset_index(drop=True)
    density = (mapped[keep].to_numpy() / area_km2[keep].to_numpy())

    variables = {
        name: np.asarray(arr)[keep]
        for name, arr in ds.variables.items()
        if name in base_names
    }
    variables["population_density"] = density

    roles = dict(ds.variable_roles)
    roles["population_density"] = "density"      # area-normalised -> Gate 1 checks CRS
    units = dict(ds.variable_units)
    units["population_density"] = "per_km2"
    cites = dict(ds.citation_by_variable or {})
    cites["population_density"] = (
        "Population: Census ACS 5-Year 2022, table B01003; "
        "density per sq km of tract polygon area."
    )

    # Rebuild spatial weights for the retained subset -- reusing the parent
    # weights after dropping rows would silently misalign the matrix.
    import libpysal
    w = libpysal.weights.Queen.from_dataframe(
        gdf, silence_warnings=True, use_index=True
    )
    if w.islands:
        alive = [i for i in range(len(gdf)) if gdf.index[i] not in w.islands]
        gdf = gdf.iloc[alive].reset_index(drop=True)
        variables = {k: v[alive] for k, v in variables.items()}
        w = libpysal.weights.Queen.from_dataframe(
            gdf, silence_warnings=True, use_index=True
        )
    w.transform = "r"

    return Dataset(
        id="atlanta-live-demo",
        gdf=gdf,
        variables=variables,
        variable_roles={k: v for k, v in roles.items() if k in variables},
        weights=w.full()[0],
        description=f"{len(gdf)} Atlanta tracts (real ACS/CDC/TIGER)",
        citation=ds.citation,
        citation_by_variable={k: v for k, v in cites.items() if k in variables},
        variable_units={k: v for k, v in units.items() if k in variables},
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt", help="what you want mapped, in plain English")
    ap.add_argument("--var", nargs="+", choices=VALID, default=["density"],
                    help="which real variables to put on the table (default: density)")
    ap.add_argument("--llm", choices=["nvidia", "mock"], default="nvidia",
                    help="nvidia = real hosted model (default); mock = offline")
    ap.add_argument("--open", action="store_true",
                    help="open the finished map in the default viewer")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")

    OUT.mkdir(parents=True, exist_ok=True)

    print(f"\n  prompt : {args.prompt!r}")
    print(f"  data   : real Atlanta tracts, variables = {args.var}")
    print(f"  llm    : {args.llm}\n")

    ds = build_dataset(args.var)
    print(f"  {len(ds.gdf)} tracts on the table: {list(ds.variables)}\n")

    if args.llm == "nvidia":
        from autocarto.semantic.nvidia_llm import NvidiaLLM
        llm = NvidiaLLM()
        print("  asking the model to plan the map ...", flush=True)
    else:
        from autocarto.semantic.llm_client import MockLLM
        llm = MockLLM()

    from autocarto.orchestrator import Orchestrator

    orch = Orchestrator(llm=llm, max_iter=3, seed=0)
    result = orch.run(args.prompt, ds)

    print()
    for i, it in enumerate(result.trace["iterations"]):
        suite = it["gate_suite"]
        prop = it["proposal"]
        print(f"  iteration {i}: {suite['decision']:<7} "
              f"map_type={prop.get('map_type')} "
              f"method={prop.get('classification_method')}")
        for g in suite["gates"]:
            if g["decision"] == "REJECT":
                why = (g.get("instruction") or "").split(".")[0]
                print(f"      x {g['gate']}: {why[:96]}")

    if not result.success:
        print(f"\n  did not converge: {result.insufficiency_report}\n")
        return 1

    fig_path = OUT / "map.png"
    result.figure.savefig(fig_path, dpi=160, bbox_inches="tight")
    (OUT / "trace.json").write_text(
        json.dumps(result.trace, indent=2, default=str), encoding="utf-8"
    )

    print(f"\n  map   -> {fig_path}")
    print(f"  trace -> {OUT / 'trace.json'}\n")

    if args.open:
        import os
        os.startfile(fig_path)  # noqa: S606 - Windows viewer, demo convenience

    return 0


if __name__ == "__main__":
    sys.exit(main())
