import { useEffect, useMemo, useRef, useState } from "react";
import type { Map as MapInstance } from "maplibre-gl";
import type { User } from "./AuthGate";
import Phase2, { EMPTY_PHASE2, type Phase2State } from "./Phase2";
import { DEFAULT_LAYER_ORDER, LAYER_NAMES, filterCollection, type LayerId } from "./layers";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUp,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Database,
  Download,
  Eye,
  EyeOff,
  Focus,
  Layers3,
  Leaf,
  LoaderCircle,
  Map as MapIcon,
  MessageSquare,
  Minus,
  MoreHorizontal,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Table2,
  TreePine,
  Users,
  Wallet,
  X,
} from "lucide-react";
import MapCanvas, {
  NJ_BOUNDS,
  basemapAttribution,
  type Basemap,
} from "./MapCanvas";
import {
  api,
  formatValue,
  methodName,
  type Catalog,
  type ChatMessage,
  type ChatResponse,
  type County,
  type GeoData,
  type MapPlan,
  type Metric,
  type Palette,
  type Settings,
  type Workspace,
  type MapView,
} from "./types";

const DEFAULTS: Settings = {
  metric: "density",
  palette: "forest",
  method: "auto",
};
const STORAGE_KEY = "cartollm-nj-workspace-v1";
const WELCOME: ChatMessage = {
  id: 0,
  role: "assistant",
  content:
    "Your New Jersey workspace is ready. Explore population, household income, and state-owned open space. Tell me what you’d like to map.",
};
const paletteOptions: { id: Palette; name: string; colors: string[] }[] = [
  {
    id: "forest",
    name: "Forest",
    colors: ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"],
  },
  {
    id: "ocean",
    name: "Ocean",
    colors: ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"],
  },
  {
    id: "violet",
    name: "Violet",
    colors: ["#f2f0f7", "#cbc9e2", "#9e9ac8", "#756bb1", "#54278f"],
  },
  {
    id: "sunset",
    name: "Sunset",
    colors: ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"],
  },
];

function loadSaved(): {
  settings: Settings;
  parks: boolean;
  basemap: Basemap;
  opacity: number;
  outlines: boolean;
} {
  try {
    const v = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (
      v &&
      ["density", "population", "income"].includes(v.settings?.metric) &&
      ["forest", "ocean", "violet", "sunset"].includes(v.settings?.palette) &&
      ["auto", "quantile", "jenks", "equal_interval"].includes(
        v.settings?.method,
      )
    ) {
      return {
        settings: v.settings,
        parks: v.parks === true,
        basemap: ["light", "dark", "satellite"].includes(v.basemap)
          ? v.basemap
          : "light",
        opacity: Number.isFinite(v.opacity)
          ? Math.max(15, Math.min(100, v.opacity))
          : 85,
        outlines: v.outlines !== false,
      };
    }
  } catch {
    /* Storage can be disabled by the browser. */
  }
  return {
    settings: DEFAULTS,
    parks: false,
    basemap: "light",
    opacity: 85,
    outlines: true,
  };
}
function download(name: string, content: string, type = "application/json") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function BoundsOf(
  geometry: GeoData["features"][number]["geometry"],
): [[number, number], [number, number]] {
  const points: number[][] = [];
  function visit(value: any) {
    if (Array.isArray(value) && typeof value[0] === "number")
      points.push(value);
    else if (Array.isArray(value)) value.forEach(visit);
  }
  if ("coordinates" in geometry) visit(geometry.coordinates);
  return [
    [
      Math.min(...points.map((p) => p[0])),
      Math.min(...points.map((p) => p[1])),
    ],
    [
      Math.max(...points.map((p) => p[0])),
      Math.max(...points.map((p) => p[1])),
    ],
  ];
}

type Project = { id: string; name: string; revision: number; workspace: Workspace };
export default function App({ user, onLogout }: { user: User | null; onLogout: () => Promise<void> }) {
  const [saved] = useState(() => user ? { settings: DEFAULTS, parks: false, basemap: "light" as Basemap, opacity: 85, outlines: true } : loadSaved());
  const [settings, setSettings] = useState<Settings>(saved.settings);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [counties, setCounties] = useState<GeoData | null>(null);
  const [parksData, setParksData] = useState<GeoData | null>(null);
  const [pointData, setPointData] = useState<GeoData | null>(null);
  const [parkPoints, setParkPoints] = useState(false);
  const [countyFilter, setCountyFilter] = useState<string[]>([]);
  const [layerOrder, setLayerOrder] = useState<LayerId[]>(DEFAULT_LAYER_ORDER);
  const [phase2, setPhase2] = useState<Phase2State>(EMPTY_PHASE2);
  const [tractPlan, setTractPlan] = useState<MapPlan | null>(null);
  const tractPlanReady = !phase2.tracts || (tractPlan?.metric === settings.metric && tractPlan.requested_palette === settings.palette && tractPlan.requested_method === settings.method);
  const saveReady = useRef(tractPlanReady);
  saveReady.current = tractPlanReady;
  const [plan, setPlan] = useState<MapPlan | null>(null);
  const [parks, setParks] = useState(saved.parks);
  const [visible, setVisible] = useState(true);
  const [basemap, setBasemap] = useState<Basemap>(saved.basemap);
  const [opacity, setOpacity] = useState(saved.opacity);
  const [outlines, setOutlines] = useState(saved.outlines);
  const [tab, setTab] = useState<"chat" | "layers" | "data">("chat");
  const [inspector, setInspector] = useState(false);
  const [mobilePanel, setMobilePanel] = useState(false);
  const [modal, setModal] = useState<
    "export" | "validation" | "sources" | null
  >(null);
  const [showTable, setShowTable] = useState(false);
  const [selected, setSelected] = useState<County | null>(null);
  const [query, setQuery] = useState("");
  const [dataSearch, setDataSearch] = useState("");
  const [countySearch, setCountySearch] = useState("");
  const [sortMetric, setSortMetric] = useState<Metric>("density");
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [useAI, setUseAI] = useState(false);
  const [busy, setBusy] = useState(false);
  const [initialError, setInitialError] = useState("");
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState("Styles saved in this browser");
  const [reload, setReload] = useState(0);
  const mapRef = useRef<MapInstance | null>(null);
  const messagesEnd = useRef<HTMLDivElement>(null);
  const modalRef = useRef<HTMLElement>(null);
  const importInput = useRef<HTMLInputElement>(null);
  const [importedView, setImportedView] = useState<MapView | null>(null);
  const [workspaceNotice, setWorkspaceNotice] = useState("");
  const displayCounties = useMemo(() => counties && filterCollection(counties, countyFilter, catalog?.counties || [], true), [counties, countyFilter, catalog]);
  const displayParks = useMemo(() => parksData && filterCollection(parksData, countyFilter, catalog?.counties || []), [parksData, countyFilter, catalog]);
  const displayPoints = useMemo(() => pointData && filterCollection(pointData, countyFilter, catalog?.counties || []), [pointData, countyFilter, catalog]);
  const [projectName, setProjectName] = useState("New Jersey explorer");
  const [projectList, setProjectList] = useState<Pick<Project, "id" | "name" | "revision">[]>([]);
  const [showProjects, setShowProjects] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [cameraRevision, setCameraRevision] = useState(0);
  const project = useRef<Pick<Project, "id" | "revision"> | null>(null);
  const lastSaved = useRef("");
  const pending = useRef(false);
  const saveBlocked = useRef(false);
  const saveFlight = useRef<Promise<void> | null>(null);
  const currentRecord = useRef(workspaceRecord);
  currentRecord.current = workspaceRecord;
  const currentName = useRef(projectName);
  currentName.current = projectName;

  function restore(record: Workspace, sourceCatalog = catalog) {
    setPhase2(record.phase2 ?? EMPTY_PHASE2);
    setCountyFilter(record.county_filter ?? []); setLayerOrder(record.layer_order ?? DEFAULT_LAYER_ORDER);
    setSettings(record.settings); setPlan(record.trace.plan); setParks(record.parks); setParkPoints(record.park_points ?? false);
    setVisible(record.visible); setOpacity(record.opacity); setOutlines(record.outlines);
    setBasemap(record.basemap); setMessages(record.messages); setImportedView(record.view);
    setSelected(sourceCatalog?.counties.find(c => c.id === record.view.selected_county) || null);
    setQuery(""); setError("");
  }

  async function saveProject() {
    if (!tractPlanReady) { setSaveStatus("Waiting for tract validation…"); return; }
    if (!user || !initialized || !mapRef.current || busy || saveBlocked.current) return;
    if (saveFlight.current) return saveFlight.current;
    const run = async () => {
      try {
        do {
          if (!saveReady.current) { pending.current = true; return; }
          pending.current = false;
          const workspace = currentRecord.current();
          const name = currentName.current.trim() || "Untitled map";
          const key = JSON.stringify({ name, workspace });
          if (key === lastSaved.current) { setSaveStatus("Saved to your account"); return; }
          setSaveStatus("Saving…");
          const previous = project.current;
          const result = await api<Pick<Project, "id" | "revision">>(previous ? `projects/${previous.id}` : "projects", { name, workspace, revision: previous?.revision || 0 }, previous ? "PUT" : "POST");
          project.current = result; lastSaved.current = key;
          setSaveStatus("Saved to your account");
        } while (pending.current);
      } catch (e) {
        // Stop after any uncertain write. Reopen retrieves the current revision;
        // blindly retrying a timed-out create could duplicate a project.
        saveBlocked.current = true; pending.current = true;
        setSaveStatus("Changes not saved"); setError((e as Error).message);
      }
    };
    saveFlight.current = run();
    await saveFlight.current; saveFlight.current = null;
  }

  useEffect(() => {
    if (!user || !initialized || !mapRef.current) return;
    pending.current = true;
    const timer = setTimeout(() => { void saveProject(); }, 1000);
    return () => clearTimeout(timer);
  }, [initialized, settings, parks, parkPoints, countyFilter, layerOrder, phase2, tractPlan, visible, opacity, outlines, basemap, selected, messages, plan, projectName, cameraRevision, busy]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (user && (pending.current || saveFlight.current)) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [user]);

  function workspaceRecord(): Workspace {
    if (!tractPlanReady) throw new Error("Wait for tract classification to finish loading before saving.");
    if (!catalog || !plan || !mapRef.current)
      throw new Error("Wait for the map to finish loading.");
    const map = mapRef.current;
    const center = map.getCenter().wrap();
    const files = catalog.manifest.files;
    return {
      kind: "workspace",
      version: 5,
      phase2: { ...phase2, tract_plan_id: phase2.tracts ? tractPlan!.plan_id : null },
      county_filter: countyFilter,
      layer_order: layerOrder,
      datasets: {
        tracts: { version_id: files["tracts.geojson"].version_id, sha256: files["tracts.geojson"].sha256 },
        park_points: { version_id: files["park_points.geojson"].version_id, sha256: files["park_points.geojson"].sha256 },
        counties: {
          version_id: files["counties.geojson"].version_id,
          sha256: files["counties.geojson"].sha256,
        },
        parks: {
          version_id: files["parks.geojson"].version_id,
          sha256: files["parks.geojson"].sha256,
        },
      },
      settings,
      parks,
      park_points: parkPoints,
      visible,
      opacity,
      outlines,
      basemap,
      view: {
        center: [center.lng, center.lat],
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
        selected_county: selected?.id || null,
      },
      messages,
      trace: {
        kind: "web-map-trace",
        version: 1,
        plan,
        parks: catalog.park_plan,
      },
    };
  }

  async function exportWorkspace() {
    if (busy) return;
    setBusy(true);
    setWorkspaceNotice("");
    try {
      const record = await api<Workspace>(
        "workspace/import",
        workspaceRecord(),
      );
      download("cartollm-workspace.json", JSON.stringify(record, null, 2));
      setWorkspaceNotice(
        "Workspace saved with map view, layers, styles, conversation, and validated trace.",
      );
    } catch (e) {
      setWorkspaceNotice((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function importWorkspace(file?: File) {
    if (!file || busy) return;
    setBusy(true);
    setWorkspaceNotice("");
    try {
      if (file.size > 1024 * 1024)
        throw new Error("Workspace exceeds the 1 MiB limit.");
      // Send original bytes so the server can reject duplicate keys as well
      // as invalid JSON, unknown versions, and mismatched snapshots.
      const response = await fetch("/api/workspace/import", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CartoLLM-Request": "1" },
        body: file,
        signal: AbortSignal.timeout(90000),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Workspace import failed.",
        );
      const record = result as Workspace;
      setPhase2(record.phase2 ?? EMPTY_PHASE2);
      setCountyFilter(record.county_filter ?? []); setLayerOrder(record.layer_order ?? DEFAULT_LAYER_ORDER);
      setSettings(record.settings);
      setPlan(record.trace.plan);
      setParks(record.parks);
      setParkPoints(record.park_points ?? false);
      setVisible(record.visible);
      setOpacity(record.opacity);
      setOutlines(record.outlines);
      setBasemap(record.basemap);
      setMessages(record.messages);
      setSelected(
        catalog?.counties.find((c) => c.id === record.view.selected_county) ||
          null,
      );
      setImportedView(record.view);
      setQuery("");
      setError("");
      setWorkspaceNotice(
        "Workspace restored. Dataset versions match and validation was recomputed.",
      );
    } catch (e) {
      setWorkspaceNotice((e as Error).message);
    } finally {
      setBusy(false);
      if (importInput.current) importInput.current.value = "";
    }
  }

  useEffect(() => {
    let active = true;
    setInitialError("");
    Promise.all([
      api<Catalog>("catalog"),
      api<GeoData>("data/counties"),
      api<GeoData>("data/parks"),
      api<MapPlan>("map", saved.settings),
      user ? api<Pick<Project, "id" | "name" | "revision">[]>("projects").then(async rows => rows.length ? api<Project>(`projects/${rows[0].id}`) : null) : Promise.resolve(null),
      api<GeoData>("data/park_points"),
    ])
      .then(([c, countiesValue, parksValue, p, stored, points]) => {
        if (active) {
          setCatalog(c);
          setCounties(countiesValue);
          setParksData(parksValue);
          setPointData(points);
          setPlan(p);
          if (stored) {
            project.current = stored; setProjectName(stored.name); restore(stored.workspace, c);
            lastSaved.current = JSON.stringify({ name: stored.name, workspace: stored.workspace });
          }
          setInitialized(true);
        }
      })
      .catch((e) => {
        if (active)
          setInitialError(e.message || "Could not connect to the map service.");
      });
    return () => {
      active = false;
    };
  }, [reload]);

  useEffect(() => {
    if (!plan || user) return;
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ settings, parks, opacity, outlines, basemap }),
      );
      setSaveStatus("Styles saved in this browser");
    } catch {
      setSaveStatus("Browser storage unavailable");
    }
  }, [settings, parks, opacity, outlines, basemap, plan]);
  useEffect(() => {
    messagesEnd.current?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }, [messages, busy]);
  useEffect(() => {
    if (!modal || !modalRef.current) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = modalRef.current;
    const focusable = () =>
      Array.from(
        dialog.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input, select, textarea, [tabindex="0"]',
        ),
      );
    focusable()[0]?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setModal(null);
      if (event.key !== "Tab") return;
      const items = focusable();
      const first = items[0];
      const last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [modal]);

  function focusCounty(name: string) {
    const county = catalog?.counties.find(
      (c) => c.name.toLowerCase() === name.toLowerCase(),
    );
    const feature = counties?.features.find(
      (f) => f.properties.name.toLowerCase() === name.toLowerCase(),
    );
    if (county && feature) {
      setSelected(county);
      mapRef.current?.fitBounds(BoundsOf(feature.geometry), {
        padding: 90,
        maxZoom: 10,
        duration: 900,
      });
    }
  }
  function resetView() {
    setSelected(null);
    mapRef.current?.fitBounds(NJ_BOUNDS, { padding: 55, duration: 800 });
  }
  async function changeSettings(next: Settings) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<MapPlan>("map", next);
      setSettings(next);
      setPlan(result);
      setVisible(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function sendMessage(text = query) {
    if (!text.trim() || busy) return;
    setQuery("");
    setTab("chat");
    setBusy(true);
    setError("");
    setMessages((m) => [...m, { id: Date.now(), role: "user", content: text }]);
    try {
      const result = await api<ChatResponse>("chat", {
        message: text,
        current: settings,
        parks,
        use_ai: useAI,
      });
      if (result.applied && result.map && result.settings) {
        setPlan(result.map);
        setSettings(result.settings);
        setParks(result.parks ?? parks);
        setVisible(true);
        if (result.county) focusCounty(result.county);
        else if (result.statewide) resetView();
      }
      setMessages((m) => [
        ...m,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: result.message,
          provider: result.provider.provider,
          result:
            result.applied && result.map
              ? {
                  title: result.map.title,
                  method: result.map.method,
                  plan_id: result.map.plan_id,
                }
              : undefined,
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: (e as Error).message,
          provider: useAI ? "nvidia" : "guided",
          error: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }
  function exportData() {
    if (phase2.tracts || phase2.distance_m !== null || phase2.overlays.length) {
      setError("Use Analysis & NJ layers to download tract analysis with its verdicts or each loaded reference snapshot with provenance.");
      return;
    }
    if (!counties || !plan || !catalog) return;
    const features: GeoData["features"] = filterCollection(counties, countyFilter, catalog.counties, true).features.map((f) => ({
      ...f,
      properties: {
        ...f.properties,
        dataset: "counties",
        mapped_metric: settings.metric,
      },
    }));
    if (parks && parksData)
      features.push(
        ...filterCollection(parksData, countyFilter, catalog.counties).features.map((f) => ({
          ...f,
          properties: { ...f.properties, dataset: "parks" },
        })),
      );
    if (parkPoints && pointData) features.push(...filterCollection(pointData, countyFilter, catalog.counties).features.map(f => ({ ...f, properties: { ...f.properties, dataset: "park_points", mapped_metric: settings.metric } })));
    download(
      "new-jersey-map.geojson",
      JSON.stringify(
        {
          type: "FeatureCollection",
          metadata: {
            county_filter: countyFilter, layer_order: layerOrder,
            filter_note: "County attributes select complete features; geometry is not clipped. Classification remains statewide.",
            sources: catalog.manifest.sources,
            notes: catalog.manifest.notes,
            datasets: catalog.manifest.files,
            parks_plan: parks ? catalog.park_plan : null,
            plan,
          },
          features,
        },
        null,
        2,
      ),
      "application/geo+json",
    );
  }
  function exportPNG() {
    if (phase2.tracts || phase2.distance_m !== null || phase2.overlays.length) {
      setError("Use Export analysis PNG preview in Analysis & NJ layers to include the tract legend, buffers, reference credits and completeness verdict.");
      return;
    }
    const map = mapRef.current;
    if (!map || !plan || !catalog) return;
    const draw = () => {
      try {
        const source = map.getCanvas();
        const canvas = document.createElement("canvas");
        canvas.width = source.width;
        const parkLegendHeight = parks
          ? catalog.park_plan.categories.length * 22 + 24
          : 0;
        canvas.height = source.height + 190 + parkLegendHeight + (parkPoints ? 24 : 0);
        const ctx = canvas.getContext("2d")!;
        ctx.fillStyle = "#fcfcf8";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(source, 0, 0);
        ctx.fillStyle = "#193c34";
        ctx.font = "bold 22px sans-serif";
        ctx.fillText(`${plan.title} · New Jersey`, 24, source.height + 36);
        ctx.font = "12px sans-serif";
        ctx.fillText(
          `${methodName(plan.method)} · ${plan.unit} · EPSG:3857 · ${countyFilter.length ? countyFilter.map(id => catalog.counties.find(c => c.id === id)?.name).join(", ") : "All counties"} · Statewide breaks`,
          24,
          source.height + 59,
        );
        plan.legend.forEach((item, index) => {
          const x = 24 + index * ((canvas.width - 48) / plan.legend.length);
          ctx.fillStyle = item.color;
          ctx.fillRect(x, source.height + 77, 28, 12);
          ctx.fillStyle = "#193c34";
          ctx.fillText(
            `${index ? ">" : ""}${formatValue(item.min, settings.metric, true)}–${formatValue(item.max, settings.metric, true)}`,
            x,
            source.height + 108,
          );
        });
        if (parks) {
          ctx.fillText(
            "NJDEP state-owned open space · FEATURE_CLASS",
            24,
            source.height + 132,
          );
          catalog.park_plan.categories.forEach((category, index) => {
            const y = source.height + 148 + index * 22;
            ctx.fillStyle = category.color;
            ctx.fillRect(24, y, 14, 12);
            ctx.fillStyle = "#193c34";
            ctx.fillText(`${category.label} (${category.count})`, 44, y + 11);
          });
        }
        ctx.fillText(
          "Sources: U.S. Census ACS 2019–2023 / NJOGIS. Open space (if shown): NJDEP layer 67.",
          24,
          source.height + 137 + parkLegendHeight,
        );
        ctx.fillText(
          `Basemap: ${basemapAttribution(basemap, catalog.offline)} · CartoLLM exploratory preview`,
          24,
          source.height + 160 + parkLegendHeight,
        );
        if (parkPoints) {
          ctx.fillStyle = "#c66b24"; ctx.beginPath(); ctx.arc(30, source.height + 181 + parkLegendHeight, 5, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = "#193c34"; ctx.fillText("Park locations · NJDEP GNIS 2016 · Public access not verified", 44, source.height + 185 + parkLegendHeight);
        }
        const link = document.createElement("a");
        link.href = canvas.toDataURL("image/png");
        link.download = "new-jersey-map.png";
        link.click();
      } catch {
        setError(
          "The browser could not export this basemap. Try the light basemap or export GeoJSON.",
        );
      }
    };
    if (map.loaded()) draw();
    else {
      map.once("idle", draw);
      map.triggerRepaint();
    }
  }

  if (initialError || !catalog || !counties || !parksData || !pointData || !plan)
    return (
      <div className="boot-screen">
        <div className="brand-symbol">
          <Layers3 size={26} />
        </div>
        <h1>CartoLLM</h1>
        {initialError ? (
          <>
            <p role="alert">{initialError}</p>
            <button className="primary" onClick={() => setReload((v) => v + 1)}>
              Retry connection
            </button>
            <small>
              Start the API with <code>autocarto-web</code>.
            </small>
          </>
        ) : (
          <>
            <LoaderCircle className="spin" />
            <p>Preparing your New Jersey workspace…</p>
          </>
        )}
      </div>
    );

  const parkDataset = catalog.datasets.find((d) => d.id === "parks")!;
  const filteredDatasets = catalog.datasets.filter((d) =>
    `${d.name} ${d.description} ${d.category}`
      .toLowerCase()
      .includes(dataSearch.toLowerCase()),
  );
  const sortedCounties = [...catalog.counties]
    .filter(c => !countyFilter.length || countyFilter.includes(c.id))
    .filter((c) => c.name.toLowerCase().includes(countySearch.toLowerCase()))
    .sort((a, b) => b[sortMetric] - a[sortMetric]);
  const gvf = Number(plan.validation.classification.diagnostics.gvf);

  return (
    <div className="workspace">
      <header className="app-header">
        <a href="/" className="brand" aria-label="CartoLLM home">
          <div className="brand-symbol">
            <Layers3 size={22} strokeWidth={1.8} />
          </div>
          <span>
            Carto<span className="brand-light">LLM</span>
          </span>
          <span className="beta">BETA</span>
        </a>
        <div className="header-divider" />
        <div className="workspace-name">
          <span>My workspace</span>
          <ChevronRight size={14} />
          {user ? <input aria-label="Project name" className="project-name" maxLength={120} value={projectName} onChange={e => setProjectName(e.target.value)} /> : <strong>New Jersey explorer</strong>}
        </div>
        <div className="header-actions">
          {user && <><button onClick={async () => { try { await saveProject(); setProjectList(await api("projects")); setShowProjects(!showProjects); } catch (e) { setError((e as Error).message); } }}>Projects</button><button disabled={busy} onClick={() => void saveProject()}>Save now</button><button onClick={async () => { await saveProject(); if (pending.current || saveBlocked.current) { setError("Export your unsaved workspace before signing out."); return; } try { await onLogout(); } catch (e) { setError((e as Error).message); } }}>Sign out</button></>}
          <span className="save-status">
            <CheckCheck size={15} />
            {saveStatus}
          </span>
          <button className="export-button" onClick={() => setModal("export")}>
            <ArrowDownToLine size={16} />
            <span>Export map</span>
          </button>
          <div className="avatar" title="Local workspace">
            NJ
          </div>
        </div>
      </header>
      {showProjects && <section className="project-menu" aria-label="Your projects"><h3>Your private projects</h3>
        {projectList.map(item => <button key={item.id} onClick={async () => {
          if (saveFlight.current) await saveFlight.current;
          if (pending.current && !window.confirm("Opening a saved map will replace unsaved changes. Continue?")) return;
          try {
            const loaded = await api<Project>(`projects/${item.id}`);
            project.current = loaded; lastSaved.current = JSON.stringify({ name: loaded.name, workspace: loaded.workspace });
            pending.current = false; saveBlocked.current = false; setProjectName(loaded.name); restore(loaded.workspace); setShowProjects(false);
          } catch (e) { setError((e as Error).message); }
        }}>{item.name}</button>)}
        <button onClick={async () => { await saveProject(); if (pending.current || saveBlocked.current) return; project.current = null; lastSaved.current = ""; setProjectName("Untitled map"); setCameraRevision(n => n + 1); setShowProjects(false); }}>Save as a new project</button>
        <button onClick={() => setShowProjects(false)}>Close</button>
      </section>}
      <nav className="rail" aria-label="Workspace navigation">
        <button
          className={tab !== "data" ? "rail-button active" : "rail-button"}
          title="Map workspace"
          aria-label="Map workspace"
          onClick={() => setTab("chat")}
        >
          <MapIcon size={21} />
        </button>
        <button
          className={tab === "data" ? "rail-button active" : "rail-button"}
          title="Data catalog"
          aria-label="Data catalog"
          onClick={() => setTab("data")}
        >
          <Database size={21} />
        </button>
        <div className="rail-bottom">
          <button
            className="rail-button"
            aria-label="Sources and workspace information"
            title="Sources & information"
            onClick={() => setModal("sources")}
          >
            <CircleHelp size={21} />
          </button>
          <span className="rail-dot" title="API connected" />
        </div>
      </nav>
      <aside className={`sidebar ${mobilePanel ? "mobile-open" : ""}`}>
        <div className="sidebar-heading">
          <div className="eyebrow">
            <span className="live-dot" />
            NEW JERSEY WORKSPACE
          </div>
          <h1>
            A little curiosity.
            <br />A whole new perspective.
          </h1>
          <p>Open data. Clearer understanding.</p>
          <button
            className="mobile-close icon-button"
            aria-label="Close sidebar"
            onClick={() => setMobilePanel(false)}
          >
            <X size={18} />
          </button>
        </div>
        <div className="tabs" role="tablist" aria-label="Workspace panels">
          {(
            [
              ["chat", MessageSquare, "Chat"],
              ["layers", Layers3, "Layers"],
              ["data", Database, "Data"],
            ] as const
          ).map(([id, Icon, label]) => (
            <button
              key={id}
              role="tab"
              aria-selected={tab === id}
              className={tab === id ? "active" : ""}
              onClick={() => setTab(id)}
            >
              <Icon size={15} />
              {label}
              {id === "layers" && (
                <span className="tab-count">{1 + Number(parks) + Number(parkPoints)}</span>
              )}
            </button>
          ))}
        </div>
        {tab === "chat" && (
          <>
            <div
              className="chat-scroll"
              role="log"
              aria-label="Mapping conversation"
              aria-live="polite"
            >
              {messages.length === 1 && (
                <div className="chat-intro">
                  <div className="agent-mark">
                    <Sparkles size={21} />
                  </div>
                  <h2>What will you discover?</h2>
                  <p>Start with a question. Make it a map.</p>
                </div>
              )}
              {messages.map((m) => (
                <div
                  className={`message ${m.role} ${m.error ? "message-error" : ""}`}
                  key={m.id}
                >
                  {m.role === "assistant" && (
                    <div className="message-byline">
                      <Sparkles size={13} />
                      <strong>Carto assistant</strong>
                      <span>
                        {m.provider === "nvidia" ? "AI intent" : "Guided"}
                      </span>
                    </div>
                  )}
                  <p>{m.content}</p>
                  {m.result && (
                    <div className="result-card">
                      <div className="result-icon">
                        <MapIcon size={18} />
                      </div>
                      <div>
                        <strong>{m.result.title}</strong>
                        <small>
                          {methodName(m.result.method)} · 21 counties
                        </small>
                      </div>
                      <Check size={15} />
                    </div>
                  )}
                </div>
              ))}
              {messages.length === 1 && (
                <div className="suggestions">
                  <span className="section-label">TRY A STARTING POINT</span>
                  <button
                    disabled={busy}
                    onClick={() =>
                      sendMessage("Show population density across New Jersey")
                    }
                  >
                    <Users size={16} />
                    <span>Where do people live?</span>
                    <ArrowRight size={15} />
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      sendMessage("Map household income in New Jersey")
                    }
                  >
                    <Wallet size={16} />
                    <span>Explore household income</span>
                    <ArrowRight size={15} />
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      sendMessage("Show state-owned open space in New Jersey")
                    }
                  >
                    <TreePine size={16} />
                    <span>Find a little more green</span>
                    <ArrowRight size={15} />
                  </button>
                </div>
              )}
              {busy && (
                <div className="thinking">
                  <LoaderCircle className="spin" size={14} />
                  Preparing and checking your map…
                </div>
              )}
              <div ref={messagesEnd} />
            </div>
            <div className="composer-area">
              <div className="mode-bar">
                <span>
                  <span className="live-dot" />
                  {useAI
                    ? "AI intent · deterministic checks"
                    : "Guided commands · no LLM calls"}
                </span>
                <button
                  className={useAI ? "mode-toggle selected" : "mode-toggle"}
                  aria-pressed={useAI}
                  disabled={!catalog.ai_available || busy}
                  title={
                    catalog.ai_available
                      ? "Toggle the configured NVIDIA intent parser"
                      : "Configure NVIDIA_API_KEY to enable AI"
                  }
                  onClick={() => setUseAI((v) => !v)}
                >
                  <Sparkles size={12} />
                  AI
                </button>
              </div>
              <form
                className="composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  sendMessage();
                }}
              >
                <textarea
                  aria-label="Ask about your map"
                  placeholder="Ask about your map…"
                  value={query}
                  maxLength={1500}
                  rows={2}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                />
                <div className="composer-bottom">
                  <span>
                    <MapIcon size={12} />
                    New Jersey open data
                  </span>
                  <button
                    className="send-button"
                    type="submit"
                    disabled={busy || !query.trim()}
                    aria-label="Send map request"
                  >
                    {busy ? (
                      <LoaderCircle size={17} className="spin" />
                    ) : (
                      <ArrowUp size={18} />
                    )}
                  </button>
                </div>
              </form>
              <p className="composer-note">
                Intent is interpreted. Map values are computed.
              </p>
            </div>
          </>
        )}
        {tab === "layers" && (
          <div className="panel-scroll layers-panel">
            <div className="panel-title">
              <h2>
                On this map <span>{1 + Number(parks) + Number(parkPoints)}</span>
              </h2>
              <button className="text-button" onClick={() => setTab("data")}>
                <Plus size={14} />
                Add data
              </button>
            </div>
            <p className="panel-description">
              Control what your map has to say.
            </p>
            <details className="county-filter"><summary>County filter · {countyFilter.length || "All 21"}</summary>
              <button onClick={() => { setPhase2(s => ({ ...s, distance_m: null, result_id: null })); setCountyFilter([]); setSelected(null); }}>Show all counties</button>
              {catalog.counties.map(c => <label key={c.id}><input type="checkbox" checked={countyFilter.includes(c.id)} onChange={() => { setPhase2(s => ({ ...s, distance_m: null, result_id: null })); setCountyFilter(ids => ids.includes(c.id) ? ids.filter(id => id !== c.id) : [...ids, c.id].sort()); setSelected(null); }} />{c.name}</label>)}
              <p>Filters use county attributes, preserving whole features. Unassigned features are hidden while filtering. Classification stays statewide.</p>
            </details>
            <section className="layer-order" aria-label="Layer drawing order"><strong>Drawing order · top first</strong>
              {[...layerOrder].reverse().map((id, topIndex) => <div key={id}><span>{LAYER_NAMES[id]}</span>
                <button aria-label={`Move ${LAYER_NAMES[id]} up`} disabled={topIndex === 0} onClick={() => setLayerOrder(order => { const next = [...order], index = next.indexOf(id); [next[index], next[index + 1]] = [next[index + 1], next[index]]; return next; })}>↑</button>
                <button aria-label={`Move ${LAYER_NAMES[id]} down`} disabled={topIndex === layerOrder.length - 1} onClick={() => setLayerOrder(order => { const next = [...order], index = next.indexOf(id); [next[index], next[index - 1]] = [next[index - 1], next[index]]; return next; })}>↓</button>
              </div>)}
            </section>
            {parks && (
              <div className="layer-card">
                <span className="layer-swatch parks-swatch">
                  <TreePine size={18} />
                </span>
                <div>
                  <strong>State-owned open space</strong>
                  <small>{parkDataset.count} polygons · NJDEP</small>
                </div>
                <button
                  className="icon-button"
                  aria-label="Remove park layer"
                  onClick={() => setParks(false)}
                >
                  <X size={16} />
                </button>
              </div>
            )}
            <div className="layer-card selected">
              <span
                className="layer-swatch"
                style={{ background: plan.colors[2] }}
              >
                <Layers3 size={17} />
              </span>
              <div>
                <strong>{plan.title}</strong>
                <small>21 counties · ACS 2019–2023</small>
              </div>
              <button
                className="icon-button"
                aria-label={visible ? "Hide county fill" : "Show county fill"}
                onClick={() => setVisible((v) => !v)}
              >
                {visible ? <Eye size={16} /> : <EyeOff size={16} />}
              </button>
            </div>
            <button className="wide-button" aria-pressed={parkPoints} onClick={() => setParkPoints(v => !v)}><TreePine size={16} />{parkPoints ? "Hide" : "Show"} historical park points</button>
            <button
              className="wide-button"
              onClick={() => setInspector((v) => !v)}
            >
              <Settings2 size={16} />
              Style selected layer
              <ChevronRight size={15} />
            </button>
            <button
              className="wide-button"
              onClick={() => setShowTable((v) => !v)}
            >
              <Table2 size={16} />
              Explore the data table
              <ChevronRight size={15} />
            </button>
            <div className="source-note">
              <ShieldCheck size={19} />
              <div>
                <strong>Every number has a source.</strong>
                <p>Versioned snapshots keep this workspace reproducible.</p>
                <button
                  className="text-button"
                  onClick={() => setModal("sources")}
                >
                  View data provenance <ArrowRight size={12} />
                </button>
              </div>
            </div>
          </div>
        )}
        {tab === "data" && (
          <div className="panel-scroll catalog-panel">
            <div className="panel-title">
              <h2>New Jersey open data</h2>
              <span className="soft-badge">{catalog.datasets.length}</span>
            </div>
            <p className="panel-description">
              A few good datasets. Endless questions.
            </p>
            <label className="search-field">
              <Search size={15} />
              <input
                aria-label="Search datasets"
                placeholder="Search the catalog"
                value={dataSearch}
                onChange={(e) => setDataSearch(e.target.value)}
              />
            </label>
            <div className="catalog-list">
              {filteredDatasets.map((d) => {
                const added =
                  d.id === "parks" ? parks : d.id === "park_points" ? parkPoints : d.id === settings.metric;
                return (
                  <article className="dataset-card" key={d.id}>
                    <div className="dataset-category">
                      <span>{d.category}</span>
                      {d.geometry === "Point" ? (
                        <TreePine size={17} />
                      ) : (
                        <Layers3 size={17} />
                      )}
                    </div>
                    <h3>{d.name}</h3>
                    <p>{d.description}</p>
                    <small>{d.source}</small>
                    <div className="dataset-footer">
                      <span>
                        {d.count}{" "}
                        {d.geometry === "Point" ? "locations" : d.id === "parks" ? "areas" : "counties"} ·{" "}
                        {d.vintage}
                      </span>
                      <button
                        disabled={busy}
                        className={added ? "add-dataset added" : "add-dataset"}
                        aria-label={
                          added ? `${d.name} is on map` : `Add ${d.name}`
                        }
                        onClick={() =>
                          d.id === "parks"
                            ? setParks((v) => !v)
                            : d.id === "park_points" ? setParkPoints(v => !v)
                            : changeSettings({ ...settings, metric: d.id })
                        }
                      >
                        {added ? <Check size={15} /> : <Plus size={15} />}
                      </button>
                    </div>
                  </article>
                );
              })}
              {!filteredDatasets.length && (
                <p className="empty-state">
                  No datasets match “{dataSearch}”. Try population, income, or
                  parks.
                </p>
              )}
            </div>
          </div>
        )}
        <div className="sidebar-footer">
          <Leaf size={13} />
          <span>Built for the Garden State.</span>
          <span className="version-label">v0.1</span>
        </div>
      </aside>
      <main className={`map-area ${phase2.tracts ? "tract-mode" : ""}`}>
        <MapCanvas
          counties={displayCounties!}
          parksData={displayParks!}
          pointData={displayPoints!}
          layerOrder={layerOrder}
          parkPoints={parkPoints}
          parkPlan={catalog.park_plan}
          view={importedView}
          plan={plan}
          parks={parks}
          visible={visible && !phase2.tracts}
          opacity={opacity}
          outlines={outlines}
          basemap={basemap}
          offline={catalog.offline}
          selected={selected}
          onSelect={setSelected}
          onReady={(map) => {
            mapRef.current = map;
            setCameraRevision(n => n + 1);
          }}
          onViewChange={() => setCameraRevision(n => n + 1)}
        />
        <Phase2 map={mapRef.current} state={phase2} onChange={next => { setPhase2(next); if (next.distance_m !== null) setParkPoints(true); }} settings={settings} counties={countyFilter} basePlan={plan} opacity={opacity} outlines={outlines} basemap={basemap} offline={catalog.offline} parks={parks} parkPoints={parkPoints} parkPlan={catalog.park_plan} onPlan={setTractPlan} />
        <div className="map-topbar">
          <button className="export-button" aria-pressed={parkPoints} onClick={() => setParkPoints(value => !value)} title={catalog.manifest.coverage.park_points}>{parkPoints ? "Hide" : "Show"} historical park points</button>
          <div className="map-location">
            <span className="location-icon">
              <MapIcon size={16} />
            </span>
            <div>
              <strong>New Jersey</strong>
              <small>
                United States <span>•</span> 21 counties
              </small>
            </div>
            <ChevronDown size={14} />
          </div>
          <div className="map-top-actions">
            <button
              className="floating-button mobile-panel-button"
              onClick={() => setMobilePanel((v) => !v)}
            >
              <MessageSquare size={16} />
              Chat
            </button>
            <button
              aria-label="Data table"
              className={`floating-button ${showTable ? "selected" : ""}`}
              onClick={() => setShowTable((v) => !v)}
            >
              <Table2 size={16} />
              <span>Data table</span>
            </button>
            <button
              aria-label="Style"
              className={`floating-button ${inspector ? "selected" : ""}`}
              onClick={() => setInspector((v) => !v)}
            >
              <Settings2 size={16} />
              <span>Style</span>
            </button>
          </div>
        </div>
        <div className="map-caption">
          <span className="caption-kicker">A STATE OF POSSIBILITY</span>
          <span>New Jersey, in perspective.</span>
        </div>
        {selected && !inspector && (
          <section className="county-card">
            <div className="panel-title">
              <span className="eyebrow">COUNTY INSIGHT</span>
              <button
                className="icon-button"
                onClick={() => setSelected(null)}
                aria-label="Close county details"
              >
                <X size={15} />
              </button>
            </div>
            <h2>
              {selected.name}
              <span>County</span>
            </h2>
            <div className="county-value">
              {formatValue(selected[settings.metric], settings.metric)}
              <small>{plan.unit}</small>
            </div>
            <div className="county-stats">
              <div>
                <span>Population</span>
                <strong>
                  {formatValue(selected.population, "population", true)}
                </strong>
              </div>
              <div>
                <span>Median income</span>
                <strong>{formatValue(selected.income, "income", true)}</strong>
              </div>
            </div>
            {settings.metric === "income" && selected.income_moe >= 0 && (
              <p className="fine-print">
                90% margin of error: ±
                {formatValue(selected.income_moe, "income")}
              </p>
            )}
            <button
              className="text-button"
              onClick={() => focusCounty(selected.name)}
            >
              <Focus size={13} />
              Zoom to county
            </button>
          </section>
        )}
        {inspector && (
          <section className="style-panel">
            <div className="style-heading">
              <div>
                <span className="eyebrow">MAKE IT YOURS</span>
                <h2>Layer style</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close style panel"
                onClick={() => setInspector(false)}
              >
                <X size={17} />
              </button>
            </div>
            <div className="style-body">
              <label className="control-label">
                Map attribute
                <select
                  value={settings.metric}
                  disabled={busy}
                  onChange={(e) =>
                    changeSettings({
                      ...settings,
                      metric: e.target.value as Metric,
                    })
                  }
                >
                  {catalog.datasets
                    .filter((d) => d.id !== "parks" && d.id !== "park_points")
                    .map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                </select>
              </label>
              <label className="control-label">
                Classification
                <select
                  value={settings.method}
                  disabled={busy}
                  onChange={(e) =>
                    changeSettings({
                      ...settings,
                      method: e.target.value as Settings["method"],
                    })
                  }
                >
                  <option value="auto">Automatic · recommended</option>
                  <option value="jenks">Natural breaks (Jenks)</option>
                  <option value="quantile">Quantiles</option>
                  <option value="equal_interval">Equal interval</option>
                </select>
              </label>
              <p className="control-hint">
                The engine may prescribe a better fit.
              </p>
              <div className="control-label">Color palette</div>
              <div className="palette-grid">
                {paletteOptions.map((p) => (
                  <button
                    key={p.id}
                    disabled={busy}
                    aria-label={`${p.name} palette`}
                    aria-pressed={settings.palette === p.id}
                    className={
                      settings.palette === p.id
                        ? "palette-option active"
                        : "palette-option"
                    }
                    onClick={() =>
                      changeSettings({ ...settings, palette: p.id })
                    }
                  >
                    <div className="color-ramp">
                      {p.colors.map((c) => (
                        <span key={c} style={{ background: c }} />
                      ))}
                    </div>
                    <span>
                      {p.name}
                      {settings.palette === p.id && <Check size={11} />}
                    </span>
                  </button>
                ))}
              </div>
              {plan.palette_adjusted && (
                <p className="style-notice">
                  <ShieldCheck size={13} />
                  Palette adjusted by the accessibility gate. The legend shows
                  the applied colors.
                </p>
              )}
              <label className="control-label range-label">
                <span>
                  Fill opacity <b>{opacity}%</b>
                </span>
                <input
                  aria-label="Fill opacity"
                  type="range"
                  min="15"
                  max="100"
                  value={opacity}
                  onChange={(e) => setOpacity(Number(e.target.value))}
                />
              </label>
              <div className="toggle-row">
                <span>County boundaries</span>
                <button
                  role="switch"
                  aria-checked={outlines}
                  aria-label="County boundaries"
                  className={`switch ${outlines ? "on" : ""}`}
                  onClick={() => setOutlines((v) => !v)}
                >
                  <span />
                </button>
              </div>
              <div className="style-divider" />
              <div className="control-label">Basemap</div>
              <div className="basemap-options">
                {(["light", "dark", "satellite"] as const).map((b) => (
                  <button
                    disabled={catalog.offline}
                    key={b}
                    onClick={() => setBasemap(b)}
                    className={`basemap-option ${basemap === b ? "active" : ""}`}
                  >
                    <div className={`basemap-sample ${b}`}>
                      <span />
                      <i />
                    </div>
                    <span>
                      {b === "light"
                        ? "Light"
                        : b === "dark"
                          ? "Dark"
                          : "Satellite"}
                    </span>
                  </button>
                ))}
              </div>
            </div>
            <div className="style-panel-footer">
              <ShieldCheck size={14} />
              Deterministic classification & palette checks
            </div>
          </section>
        )}
        <div className={`map-bottom ${showTable ? "table-open" : ""}`}>
          <section className="map-legend">
            <div className="legend-heading">
              <div className="legend-icon">
                <Layers3 size={15} />
              </div>
              <div>
                <h2>{plan.title}</h2>
                <span>{plan.unit}</span>
              </div>
              <button
                className="icon-button"
                aria-label="Open map styling"
                onClick={() => setInspector((v) => !v)}
              >
                <MoreHorizontal size={17} />
              </button>
            </div>
            {!visible && <p className="hidden-note">County fill is hidden</p>}
            <div className="legend-rows">
              {plan.legend.map((l, i) => (
                <div className="legend-row" key={i}>
                  <span
                    className="legend-swatch"
                    style={{ background: l.color }}
                  />
                  <span>
                    {i > 0 ? "> " : ""}
                    {formatValue(l.min, settings.metric)} –{" "}
                    {formatValue(l.max, settings.metric)}
                  </span>
                </div>
              ))}
            </div>
            {parks && (
              <div className="open-space-legend">
                <strong>State-owned open space</strong>
                {catalog.park_plan.categories.map((category) => (
                  <div className="park-legend" key={category.value}>
                    <span
                      style={{ background: category.color, borderRadius: 2 }}
                    />
                    {category.label}
                    <small>{category.count}</small>
                  </div>
                ))}
              </div>
            )}
            {parkPoints && <div className="park-legend"><span style={{ color: "#c66b24" }}>●</span> GNIS park locations · 2016<br />Public access not verified</div>}
            {countyFilter.length > 0 && <p className="filter-note">{countyFilter.length} counties selected · statewide class breaks</p>}
            <div className="legend-footer">
              {methodName(plan.method)} <span>·</span> {plan.colors.length}{" "}
              classes
            </div>
          </section>
          <div className="map-controls">
            <button
              aria-label="Zoom in"
              onClick={() => mapRef.current?.zoomIn()}
            >
              <Plus size={18} />
            </button>
            <button
              aria-label="Zoom out"
              onClick={() => mapRef.current?.zoomOut()}
            >
              <Minus size={18} />
            </button>
            <div />
            <button
              aria-label="Fit New Jersey"
              title="Fit New Jersey"
              onClick={resetView}
            >
              <Focus size={18} />
            </button>
          </div>
        </div>
        <div className="map-status">
          <button onClick={() => setModal("validation")}>
            <ShieldCheck size={14} />
            <span>County G2/G5 audit</span>
            <span className="status-dot" />
          </button>
          <span className="map-status-source">ACS 2019–2023 · NJOGIS</span>
          <button className="source-link" onClick={() => setModal("sources")}>
            Sources & notes
          </button>
        </div>
        {showTable && (
          <section className="data-table-panel">
            <div className="table-toolbar">
              <div>
                <Table2 size={16} />
                <strong>County data</strong>
                <span>{sortedCounties.length} features</span>
              </div>
              <label className="table-search">
                <Search size={14} />
                <input
                  placeholder="Find a county"
                  aria-label="Find a county"
                  value={countySearch}
                  onChange={(e) => setCountySearch(e.target.value)}
                />
              </label>
              <button
                className="icon-button"
                title="Download GeoJSON"
                aria-label="Download GeoJSON"
                onClick={exportData}
              >
                <Download size={16} />
              </button>
              <button
                className="icon-button"
                aria-label="Close data table"
                onClick={() => setShowTable(false)}
              >
                <X size={17} />
              </button>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>County</th>
                    {(["population", "density", "income"] as const).map((m) => (
                      <th key={m}>
                        <button onClick={() => setSortMetric(m)}>
                          {m === "population"
                            ? "Population"
                            : m === "density"
                              ? "People / sq mi"
                              : "Median income"}
                          {sortMetric === m && <ChevronDown size={12} />}
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedCounties.map((c) => (
                    <tr
                      key={c.id}
                      className={selected?.id === c.id ? "selected" : ""}
                    >
                      <td>
                        <button onClick={() => focusCounty(c.name)}>
                          {c.name}
                          <ArrowRight size={12} />
                        </button>
                      </td>
                      <td>{formatValue(c.population, "population")}</td>
                      <td>{formatValue(c.density, "density")}</td>
                      <td>{formatValue(c.income, "income")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
        {error && (
          <div className="toast" role="alert">
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {busy && (
          <div className="map-working">
            <LoaderCircle size={14} className="spin" />
            Updating map
          </div>
        )}
      </main>
      {modal && (
        <div className="modal-backdrop" onClick={() => setModal(null)}>
          <section
            ref={modalRef}
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close icon-button"
              aria-label="Close dialog"
              onClick={() => setModal(null)}
            >
              <X size={20} />
            </button>
            {modal === "export" && (
              <>
                <span className="eyebrow">TAKE YOUR WORK WITH YOU</span>
                <h2 id="modal-title">A map worth sharing.</h2>
                <p>
                  Export your current view or keep exploring with the underlying
                  data.
                </p>
                <button className="export-option" onClick={exportPNG}>
                  <MapIcon size={23} />
                  <div>
                    <strong>Map image</strong>
                    <span>PNG with a legend, source credits, and CRS</span>
                  </div>
                  <Download size={18} />
                </button>
                <button className="export-option" onClick={exportData}>
                  <Database size={23} />
                  <div>
                    <strong>Geographic data</strong>
                    <span>
                      GeoJSON · county data and enabled open-space polygons
                    </span>
                  </div>
                  <Download size={18} />
                </button>
                <button
                  className="export-option"
                  onClick={exportWorkspace}
                  disabled={busy}
                >
                  <Layers3 size={23} />
                  <div>
                    <strong>Workspace record</strong>
                    <span>
                      Versioned JSON · map view, conversation, styles, and trace
                    </span>
                  </div>
                  <Download size={18} />
                </button>
                <button
                  className="export-option"
                  disabled={busy}
                  onClick={() => importInput.current?.click()}
                >
                  <Layers3 size={23} />
                  <div>
                    <strong>Import workspace</strong>
                    <span>Restore a v2 workspace · maximum 1 MiB</span>
                  </div>
                  <ArrowRight size={18} />
                </button>
                <input
                  ref={importInput}
                  type="file"
                  accept=".json,application/json"
                  aria-label="Workspace JSON file"
                  hidden
                  onChange={(e) => void importWorkspace(e.target.files?.[0])}
                />
                {workspaceNotice && (
                  <p className="fine-print" role="status">
                    {workspaceNotice}
                  </p>
                )}
                <p className="fine-print">
                  Map styles are saved in this browser. Hosted sharing and team
                  collaboration are not configured.
                </p>
              </>
            )}
            {modal === "validation" && (
              <>
                <span className="eyebrow">THE MATH BEHIND THE MAP</span>
                <h2 id="modal-title">Made to be inspected.</h2>
                <p>
                  The web adapter reuses the original agent’s classification and
                  color accessibility gates.
                </p>
                <div className="validation-item">
                  <ShieldCheck size={20} />
                  <div>
                    <strong>
                      G2 · Classification{" "}
                      <span className="soft-badge">
                        {plan.validation.classification.decision}
                      </span>
                    </strong>
                    <p>
                      {methodName(plan.method)} · {plan.colors.length} classes ·
                      goodness of variance fit{" "}
                      {Number.isFinite(gvf)
                        ? `${(gvf * 100).toFixed(1)}%`
                        : "unavailable"}
                    </p>
                  </div>
                </div>
                <div className="validation-item">
                  <ShieldCheck size={20} />
                  <div>
                    <strong>
                      G5 · Palette{" "}
                      <span className="soft-badge">
                        {plan.validation.color.decision}
                      </span>
                    </strong>
                    <p>
                      Opaque palette checked under three color vision deficiency
                      simulations.
                    </p>
                  </div>
                </div>
                <div className="validation-note">
                  {parks && (
                    <p>
                      <strong>
                        G5 · Open-space categories:{" "}
                        {catalog.park_plan.validation.color.decision}
                      </strong>
                      <br />
                      {catalog.park_plan.validation.scope}
                    </p>
                  )}
                  {plan.validation.scope}
                  <br />
                  <br />
                  {plan.validation.display_note}
                </div>
                <div className="trace-id">
                  <span>Reproducible plan</span>
                  <code>{plan.plan_id}</code>
                </div>
                <button
                  className="wide-button"
                  onClick={() =>
                    download(
                      `validation-${plan.plan_id}.json`,
                      JSON.stringify(
                        {
                          kind: "web-map-trace",
                          version: 1,
                          plan,
                          parks: catalog.park_plan,
                        },
                        null,
                        2,
                      ),
                    )
                  }
                >
                  <Download size={16} />
                  Download validation trace
                  <ArrowRight size={15} />
                </button>
              </>
            )}
            {modal === "sources" && (
              <>
                <span className="eyebrow">OPEN DATA, OPEN PROCESS</span>
                <h2 id="modal-title">Know what’s on your map.</h2>
                <p>
                  Preloaded, versioned data from public agencies. Retrieved{" "}
                  {new Date(catalog.manifest.retrieved_at).toLocaleDateString(
                    "en-US",
                    { year: "numeric", month: "long", day: "numeric" },
                  )}
                  .
                </p>
                <div className="source-links">
                  <a
                    href={catalog.manifest.sources.demographics}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <Users size={18} />
                    <div>
                      <strong>U.S. Census Bureau</strong>
                      <span>2019–2023 ACS 5-year population & income</span>
                    </div>
                    <ArrowRight size={16} />
                  </a>
                  <a
                    href={catalog.manifest.sources.counties}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <MapIcon size={18} />
                    <div>
                      <strong>NJ Office of GIS</strong>
                      <span>21 county boundaries and boundary area</span>
                    </div>
                    <ArrowRight size={16} />
                  </a>
                  <a
                    href={catalog.manifest.sources.parks}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <TreePine size={18} />
                    <div>
                      <strong>NJDEP · State-owned open space</strong>
                      <span>
                        {parkDataset.count} polygons · layer 67 · pinned{" "}
                        {catalog.manifest.retrieved_at.slice(0, 10)}
                      </span>
                    </div>
                    <ArrowRight size={16} />
                  </a>
                </div>
                <ul className="source-notes">
                  {Object.entries(catalog.manifest.coverage).map(
                    ([dataset, note]) => (
                      <li key={dataset}>{note}</li>
                    ),
                  )}
                  {catalog.manifest.notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
                <p className="fine-print">
                  The web map is an exploratory view. The full CLI publication
                  pipeline remains available separately.
                </p>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
