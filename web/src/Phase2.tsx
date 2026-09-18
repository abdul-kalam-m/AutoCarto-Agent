import { useEffect, useRef, useState } from "react";
import maplibregl, { type Map as MapInstance, type GeoJSONSource, type ExpressionSpecification } from "maplibre-gl";
import { api, formatValue, methodName, type Gate, type GeoData, type MapPlan, type Settings, type ParkPlan } from "./types";
import { basemapAttribution, type Basemap } from "./MapCanvas";

export type Phase2State = { tracts: boolean; tract_plan_id?: string | null; distance_m: number | null; result_id: string | null; overlays: string[] };
export const EMPTY_PHASE2: Phase2State = { tracts: false, distance_m: null, result_id: null, overlays: [] };
type Reference = { id: string; name: string; url: string; color: string; geometry: string; note: string };
type Loaded = { data: GeoData; provenance: Record<string, unknown> };
type Operation = { applied: boolean; trace: Gate[]; buffers?: GeoData; record?: { result_id: string; matched_tract_ids: string[]; tracts_considered: number; [key: string]: unknown } };
const EMPTY: GeoData = { type: "FeatureCollection", features: [] };
function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: "application/json" }));
  const link = document.createElement("a"); link.href = url; link.download = name; link.click(); URL.revokeObjectURL(url);
}

export default function Phase2({ map, state, onChange, settings, counties, basePlan, opacity, outlines, basemap, offline, parks, parkPoints, parkPlan, onPlan }: {
  map: MapInstance | null; state: Phase2State; onChange: (value: Phase2State) => void;
  settings: Settings; counties: string[]; basePlan: MapPlan; opacity: number; outlines: boolean;
  basemap: Basemap; offline: boolean;
  parks: boolean; parkPoints: boolean; parkPlan: ParkPlan;
  onPlan: (plan: MapPlan | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [tracts, setTracts] = useState<GeoData | null>(null);
  const [plan, setPlan] = useState<MapPlan | null>(null);
  const [distance, setDistance] = useState("500");
  const [result, setResult] = useState<Operation | null>(null);
  const [sources, setSources] = useState<Reference[]>([]);
  const [loaded, setLoaded] = useState<Record<string, Loaded>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [geometry, setGeometry] = useState<Gate[]>([]);
  const [completeness, setCompleteness] = useState<Gate | null>(null);
  const [exportVerdict, setExportVerdict] = useState<Gate | null>(null);
  const legend = useRef<HTMLElement>(null);
  const errorNode = useRef<HTMLParagraphElement>(null);
  const requestVersion = useRef(0);
  const countyKey = counties.join(",");
  const activePlan = state.tracts ? plan : basePlan;
  const current = useRef({ state, counties, tracts, plan, result, loaded, sources, opacity, outlines });
  current.current = { state, counties, tracts, plan, result, loaded, sources, opacity, outlines };
  useEffect(() => { if (error) errorNode.current?.scrollIntoView({ block: "nearest" }); }, [error]);

  useEffect(() => { api<Reference[]>("reference-layers").then(setSources).catch(e => setError(e.message)); }, []);
  useEffect(() => {
    let cancelled = false;
    setGeometry([]);
    api<Gate[]>(`geometry-checks/${state.tracts ? "tracts" : "counties"}?metric=${settings.metric}`).then(value => { if (!cancelled) setGeometry(value); }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [state.tracts, settings.metric]);
  useEffect(() => {
    let cancelled = false;
    if (!state.tracts) { onPlan(null); return; }
    Promise.all([tracts ? Promise.resolve(tracts) : api<GeoData>("data/tracts"), api<MapPlan>("tract-map", settings)])
      .then(([data, next]) => { if (!cancelled) { setTracts(data); setPlan(next); onPlan(next); } })
      .catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [state.tracts, settings]);

  // Restore saved operations from pinned inputs. No live reference network
  // calls occur during workspace restore; those require Load this view.
  useEffect(() => {
    let cancelled = false;
    requestVersion.current++;
    setResult(null);
    if (state.distance_m === null) return;
    setDistance(String(state.distance_m));
    api<Operation>("proximity", { distance_m: state.distance_m, counties }).then(value => {
      if (cancelled) return;
      if (!value.applied || value.record?.result_id !== state.result_id) throw new Error("Saved proximity result does not match. Run the operation again.");
      setResult(value);
    }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [state.distance_m, state.result_id, countyKey]);

  async function run() {
    const revision = ++requestVersion.current;
    setBusy(true); setError(""); setResult(null);
    try {
      const value = await api<Operation>("proximity", { distance_m: Number(distance), source: "park_points", counties });
      if (revision !== requestVersion.current) return;
      setResult(value);
      if (value.applied) onChange({ ...state, tracts: true, distance_m: Number(distance), result_id: value.record!.result_id });
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function load(source: Reference) {
    if (!map) return;
    setBusy(true); setError("");
    const bounds = map.getBounds();
    try {
      const value = await api<Loaded>(`reference-layers/${source.id}`, { bounds: [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()] });
      setLoaded(previous => ({ ...previous, [source.id]: value }));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function exportPNG() {
    if (!map || !activePlan) return;
    setError("");
    try {
      const source = map.getCanvas();
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(source.width, 760);
      canvas.height = source.height + 820;
      const ctx = canvas.getContext("2d")!;
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(source, 0, 0);
      let y = source.height + 30;
      const line = (text: string) => {
        // Wrap long attribution and source text rather than clipping it.
        let row = "";
        for (const word of text.split(" ")) {
          if (ctx.measureText(`${row} ${word}`).width > canvas.width - 48) { ctx.fillText(row, 24, y); y += 18; row = word; }
          else row += `${row ? " " : ""}${word}`;
        }
        ctx.fillText(row, 24, y); y += 22;
      };
      ctx.fillStyle = "#193c34"; ctx.font = "bold 18px sans-serif"; line(activePlan.title);
      ctx.font = "12px sans-serif"; line(`${methodName(activePlan.method)} · ${activePlan.unit} · statewide breaks · EPSG:3857`);
      for (const [index, item] of activePlan.legend.entries()) {
        ctx.fillStyle = item.color; ctx.fillRect(24, y - 11, 18, 12); ctx.fillStyle = "#193c34";
        ctx.fillText(`${index ? "> " : ""}${formatValue(item.min, activePlan.metric)} – ${formatValue(item.max, activePlan.metric)}`, 48, y); y += 19;
      }
      if (state.tracts) line(`Gray: no data (${activePlan.summary.missing ?? 0}).`);
      if (result?.record) line(`Teal: ${state.distance_m} m buffers around GNIS 2016 park points. Black outlines: ${result.record.matched_tract_ids.length} intersecting tracts. Orange points: historical park locations. Public access not verified.`);
      if (parkPoints && !result?.record) line("Orange points: historical GNIS 2016 park locations, NJDEP layer 5. Public access not verified.");
      if (parks) {
        line("NJDEP state-owned open space, layer 67 · FEATURE_CLASS");
        for (const category of parkPlan.categories) {
          ctx.fillStyle = category.color; ctx.fillRect(24, y - 11, 18, 12); ctx.fillStyle = "#193c34"; ctx.fillText(category.label, 48, y); y += 19;
        }
      }
      line(activePlan.source);
      line(`Basemap: ${basemapAttribution(basemap, offline)}.`);
      for (const item of sources.filter(s => state.overlays.includes(s.id))) line(`${item.name} (${item.color}): NJOGIS / NJDEP / FEMA. ${loaded[item.id]?.data.features.length ?? 0} features in a fixed loaded extent; live reference only.`);
      line("Exploratory preview. G4 rejects this display for area comparison. Geometric proximity is not walking access or residents served.");
      // Canvas capture excludes the HTML scale control. Report its absence.
      const verdict = await api<Gate>("render-check", { title: activePlan.title, legend_present: true, scale_bar_present: false, data_citation: activePlan.source, crs_note: "EPSG:3857", classification_note: methodName(activePlan.method) });
      setExportVerdict(verdict); line(`PNG completeness G6: ${verdict.decision} (no scale bar).`);
      if (y > canvas.height - 8) throw new Error("The PNG legend needs more space; download GeoJSON with its verdicts instead.");
      const output = document.createElement("canvas"); output.width = canvas.width; output.height = y + 16; output.getContext("2d")!.drawImage(canvas, 0, 0);
      const link = document.createElement("a"); link.href = output.toDataURL("image/png"); link.download = "nj-analysis-preview.png"; link.click();
    } catch (e) { setError(`PNG export failed: ${(e as Error).message}`); }
  }

  useEffect(() => {
    if (!map) return;
    function draw() {
      if (!map || !map.getLayer("county-fill")) return;
      const p = current.current;
      function source(id: string, data: GeoData) {
        if (!map!.getSource(id)) map!.addSource(id, { type: "geojson", data });
        else (map!.getSource(id) as GeoJSONSource).setData(data);
      }
      const data = p.tracts ? { ...p.tracts, features: p.tracts.features.filter(f => !p.counties.length || p.counties.includes(f.properties.county_id)) } : EMPTY;
      source("p2-tracts", data);
      if (!map.getLayer("p2-tract-fill")) {
        map.addLayer({ id: "p2-tract-fill", type: "fill", source: "p2-tracts", paint: { "fill-opacity": .8 } });
        map.addLayer({ id: "p2-tract-line", type: "line", source: "p2-tracts", paint: { "line-color": "#444", "line-width": .35 } });
        map.addLayer({ id: "p2-matches", type: "line", source: "p2-tracts", paint: { "line-color": "#111", "line-width": 2.5 } });
      }
      if (p.plan) {
        const expression: any[] = ["step", ["get", p.plan.metric], p.plan.colors[0]];
        p.plan.breaks.slice(1, -1).forEach((boundary, index) => expression.push(boundary + Math.max(1, Math.abs(boundary)) * 1e-12, p.plan!.colors[index + 1]));
        map.setPaintProperty("p2-tract-fill", "fill-color", ["case", ["==", ["get", p.plan.metric], null], "#b5b5b5", expression as ExpressionSpecification]);
      }
      for (const id of ["p2-tract-fill", "p2-tract-line", "p2-matches"]) map.setLayoutProperty(id, "visibility", p.state.tracts ? "visible" : "none");
      for (const id of ["p2-tract-fill", "p2-tract-line", "p2-matches", "p2-buffer-fill", "p2-buffer-line"]) if (map.getLayer(id)) map.moveLayer(id);
      map.setPaintProperty("p2-tract-fill", "fill-opacity", p.opacity / 100);
      map.setLayoutProperty("p2-tract-line", "visibility", p.state.tracts && p.outlines ? "visible" : "none");
      map.setFilter("p2-matches", ["in", ["get", "id"], ["literal", p.result?.record?.matched_tract_ids || []]]);
      source("p2-buffers", p.result?.buffers || EMPTY);
      if (!map.getLayer("p2-buffer-fill")) {
        map.addLayer({ id: "p2-buffer-fill", type: "fill", source: "p2-buffers", paint: { "fill-color": "#007f89", "fill-opacity": .15 } });
        map.addLayer({ id: "p2-buffer-line", type: "line", source: "p2-buffers", paint: { "line-color": "#007f89", "line-width": 1.8 } });
      }
      const order = [...p.state.overlays, ...p.sources.map(s => s.id).filter(id => !p.state.overlays.includes(id))];
      for (const key of order) {
        const item = p.sources.find(s => s.id === key); if (!item) continue;
        const id = `p2-ref-${key}`;
        source(id, p.loaded[key]?.data || EMPTY);
        if (!map.getLayer(id)) {
          if (item.geometry === "point") map.addLayer({ id, type: "circle", source: id, paint: { "circle-color": item.color, "circle-radius": 6, "circle-stroke-width": 1, "circle-stroke-color": "white" } });
          else map.addLayer({ id, type: "line", source: id, paint: { "line-color": item.color, "line-width": 1.5 } });
        }
        map.setLayoutProperty(id, "visibility", p.state.overlays.includes(key) ? "visible" : "none");
        map.moveLayer(id);
      }
      if (map.getLayer("park-points")) map.moveLayer("park-points");
      if (map.getLayer("place-labels")) map.moveLayer("place-labels");
    }
    draw();
    map.on("style.load", draw);
    const timer = setTimeout(draw, 300);
    return () => { map.off("style.load", draw); clearTimeout(timer); };
  }, [map, state, countyKey, tracts, plan, result, loaded, sources, opacity, outlines]);

  useEffect(() => {
    if (!map) return;
    const click = (event: maplibregl.MapMouseEvent) => {
      if (!current.current.state.tracts || !map.getLayer("p2-tract-fill")) return;
      const feature = map.queryRenderedFeatures(event.point, { layers: ["p2-tract-fill"] })[0];
      if (!feature) return;
      const p = feature.properties; const node = document.createElement("div");
      node.textContent = `${p.name}. Population: ${p.population ?? "No data"} (90% MOE ±${p.population_moe ?? "unavailable"}). Median income: ${p.income ?? "No data"} (90% MOE ±${p.income_moe ?? "unavailable"}).`;
      new maplibregl.Popup().setLngLat(event.lngLat).setDOMContent(node).addTo(map);
    };
    map.on("click", click); return () => { map.off("click", click); };
  }, [map]);

  useEffect(() => {
    if (!map || !activePlan) return;
    let cancelled = false;
    const check = () => {
      const own = legend.current;
      const displayed = (node: Element | null) => !!node && node.getBoundingClientRect().width > 0 && getComputedStyle(node).visibility !== "hidden";
      api<Gate>("render-check", { title: displayed(own) ? activePlan.title : null,
        legend_present: state.tracts ? displayed(own) : displayed(document.querySelector(".map-legend")), scale_bar_present: displayed(map.getContainer().querySelector(".maplibregl-ctrl-scale")),
        data_citation: displayed(own) ? activePlan.source : null, crs_note: displayed(own) ? "EPSG:3857" : null,
        classification_note: displayed(own) ? methodName(activePlan.method) : null }).then(value => { if (!cancelled) setCompleteness(value); }).catch(e => { if (!cancelled) setError(e.message); });
    };
    const timer = setTimeout(check, 500); window.addEventListener("resize", check);
    return () => { cancelled = true; clearTimeout(timer); window.removeEventListener("resize", check); };
  }, [map, activePlan, state.tracts]);

  const gates = [...geometry, ...(activePlan?.validation.trace || []), ...(completeness ? [completeness] : []), ...(result?.trace || [])];
  return <>
    <button className="phase2-toggle" onClick={() => setOpen(!open)}>Analysis & NJ layers {open ? "×" : "+"}</button>
    {open && <section className="phase2-panel" aria-label="Analysis and NJ layers">
      <h2>Tracts & park proximity</h2>
      <label><input type="checkbox" checked={state.tracts} onChange={e => onChange({ ...state, tracts: e.target.checked })} />Show census tract demographics</label>
      <p>2,181 tracts · ACS 2019–2023. Use Style to change the metric and palette. County filters select target tracts; breaks remain statewide.</p>
      <label>Buffer distance (metres)<input aria-label="Buffer distance in metres" type="number" min="1" max="10000" value={distance} onChange={e => setDistance(e.target.value)} /></label>
      <p>Source: 394 NJ park points (GNIS 2016). All NJ points are considered, including across county borders. Entrances and public access are unverified.</p>
      <button disabled={busy || !distance.trim()} onClick={run}>{busy ? "Working…" : "Buffer park points & intersect tracts"}</button>
      <button onClick={() => { requestVersion.current++; setResult(null); onChange({ ...state, distance_m: null, result_id: null }); }}>Clear operation</button>
      {result?.record && <p role="status"><strong>{result.record.matched_tract_ids.length} of {result.record.tracts_considered} tracts intersect.</strong> Boundary touches count; this is not walking access or population served.</p>}
      {error && <p ref={errorNode} role="alert">{error}</p>}
      <h3>Additional NJ reference layers</h3>
      <p>Zoom to a neighborhood, select a layer, then load this view. Loaded extents stay fixed as you pan. Live reference layers are excluded from analysis and must be reloaded after reopening a workspace.</p>
      {sources.map(source => <div className="reference-row" key={source.id}>
        <label><input type="checkbox" checked={state.overlays.includes(source.id)} onChange={e => onChange({ ...state, overlays: e.target.checked ? [...state.overlays, source.id] : state.overlays.filter(id => id !== source.id) })} /><span style={{ color: source.color }}>■</span> {source.name}</label>
        <button disabled={busy || !state.overlays.includes(source.id)} onClick={() => load(source)}>Load this view</button>
        {state.overlays.includes(source.id) && <button disabled={state.overlays.at(-1) === source.id} onClick={() => onChange({ ...state, overlays: [...state.overlays.filter(id => id !== source.id), source.id] })}>Move to top</button>}
        <small>{loaded[source.id] ? `${loaded[source.id].data.features.length} features loaded` : "Not loaded"} · <a href={source.url} target="_blank" rel="noreferrer">Official source</a><br />{source.note}</small>
        {loaded[source.id] && <button onClick={() => download(`${source.id}-reference.geojson`, { ...loaded[source.id].data, provenance: loaded[source.id].provenance })}>Download this snapshot</button>}
      </div>)}
      <h3>Gate verdicts</h3>
      <p>G4 rejects Web Mercator for area comparison. G1 checks the selected metric's CRS requirements (density also rejects). This display remains exploratory; distance calculations use EPSG:32111. G5 covers opaque demographic colors, not transparency or overlay contrast.</p>
      {gates.map((gate, i) => <details key={`${gate.gate}-${i}`}><summary>{gate.gate}: {gate.decision}</summary><pre>{JSON.stringify(gate, null, 2)}</pre></details>)}
      <button onClick={() => download("map-and-operation-verdicts.json", { plan: activePlan, gates, operation: result?.record || null })}>Download verdicts</button>
      {result?.record && <button onClick={() => download("spatial-operation-trace.json", result.record)}>Download versioned operation trace</button>}
      <button disabled={!activePlan || busy} onClick={exportPNG}>Export analysis PNG preview</button>
      {exportVerdict && <p>PNG G6: {exportVerdict.decision}. The exported canvas has no scale bar; it is an exploratory preview.</p>}
      <button disabled={!tracts || !plan} onClick={() => download("nj-tract-analysis.geojson", { type: "FeatureCollection", features: [...(tracts?.features.filter(f => !counties.length || counties.includes(f.properties.county_id)) || []), ...(result?.buffers?.features || [])], metadata: { plan, operation: result?.record || null, gates } })}>Download tract analysis GeoJSON</button>
    </section>}
    <section ref={legend} className={`phase2-legend ${state.tracts ? "tract-legend" : "county-audit"}`} aria-label="Map projection and tract legend">
      <strong>{activePlan?.title || "Loading tract classification…"}</strong>
      {state.tracts && plan && <><div>{plan.legend.map((item, i) => <div key={i}><span style={{ background: item.color }}>　</span> {i ? "> " : ""}{formatValue(item.min, plan.metric)} – {formatValue(item.max, plan.metric)}</div>)}<div><span style={{ background: "#b5b5b5" }}>　</span> No data ({String(plan.summary.missing ?? 0)})</div></div><small>{methodName(plan.method)} · statewide breaks</small></>}
      {!state.tracts && <small>{methodName(basePlan.method)} · see demographic legend</small>}
      {result?.record && <small>Teal: {state.distance_m} m point buffers · black outlines: {result.record.matched_tract_ids.length} intersecting tracts</small>}
      <small>{activePlan?.source}</small><small>EPSG:3857 · G4 rejects area-comparison display</small>
      {state.overlays.length > 0 && <small>Live references: {sources.filter(s => state.overlays.includes(s.id)).map(s => s.name).join(", ")} · NJOGIS / NJDEP / FEMA</small>}
    </section>
  </>;
}
