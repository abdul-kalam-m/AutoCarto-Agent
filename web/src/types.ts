import type { FeatureCollection, Geometry } from "geojson";

export type Metric = "density" | "population" | "income";
export type Palette = "forest" | "ocean" | "violet" | "sunset";
export type Settings = {
  metric: Metric;
  palette: Palette;
  method: "auto" | "quantile" | "jenks" | "equal_interval";
};
export type County = {
  id: string;
  name: string;
  population: number;
  income: number;
  density: number;
  income_moe: number;
  population_moe: number;
  area_sq_miles: number;
};
export type GeoData = FeatureCollection<Geometry, Record<string, any>>;
export type Gate = {
  gate: string;
  decision: string;
  diagnostics: Record<string, unknown>;
  instruction?: string;
};
export type MapPlan = {
  dataset_sha256: string;
  dataset_version_id: string;
  plan_id: string;
  metric: Metric;
  title: string;
  unit: string;
  method: string;
  source: string;
  requested_palette: Palette;
  requested_method: Settings["method"];
  palette_adjusted: boolean;
  breaks: number[];
  colors: string[];
  legend: { min: number; max: number; color: string; inclusive_min: boolean }[];
  summary: { min: number; max: number; top_county: string; count: number; missing?: number };
  validation: {
    classification: Gate;
    color: Gate;
    trace: Gate[];
    scope: string;
    display_note: string;
  };
};
export type ParkPlan = {
  dataset_sha256: string;
  dataset_version_id: string;
  field: "FEATURE_CLASS";
  categories: { value: string; label: string; color: string; count: number }[];
  validation: { color: Gate; trace: Gate[]; scope: string };
  plan_id: string;
};
export type MapView = {
  center: [number, number];
  zoom: number;
  bearing: number;
  pitch: number;
  selected_county: string | null;
};
export type Workspace = {
  kind: "workspace";
  version: 2 | 3 | 4 | 5;
  phase2?: import("./Phase2").Phase2State;
  county_filter?: string[];
  layer_order?: import("./layers").LayerId[];
  datasets: Record<
    "counties" | "parks",
    { version_id: string; sha256: string }
  > & { park_points?: { version_id: string; sha256: string }; tracts?: { version_id: string; sha256: string } };
  settings: Settings;
  parks: boolean;
  park_points?: boolean;
  visible: boolean;
  opacity: number;
  outlines: boolean;
  basemap: "light" | "dark" | "satellite";
  view: MapView;
  messages: ChatMessage[];
  trace: { kind: "web-map-trace"; version: 1; plan: MapPlan; parks: ParkPlan };
};
export type Dataset = {
  id: Metric | "parks" | "park_points";
  name: string;
  unit: string;
  count: number;
  description: string;
  category: string;
  geometry: string;
  source: string;
  vintage: string;
  url: string;
};
export type Catalog = {
  park_plan: ParkPlan;
  datasets: Dataset[];
  population: number;
  counties: County[];
  ai_available: boolean;
  offline: boolean;
  manifest: {
    files: Record<
      string,
      { sha256: string; version_id: string; features: number }
    >;
    coverage: Record<string, string>;
    retrieved_at: string;
    sources: Record<string, string>;
    notes: string[];
  };
};
export type ChatMessage = {
  id: number;
  role: "assistant" | "user";
  content: string;
  provider?: string;
  result?: { title: string; method: string; plan_id: string };
  error?: boolean;
};
export type ChatResponse = {
  applied: boolean;
  message: string;
  map?: MapPlan;
  settings?: Settings;
  parks?: boolean;
  county?: string;
  statewide?: boolean;
  provider: { provider: string };
};

export function formatValue(value: number, metric: Metric, compact = false) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: compact ? 1 : 0,
    ...(compact ? { notation: "compact" as const } : {}),
    ...(metric === "income" ? { style: "currency", currency: "USD" } : {}),
  }).format(value);
}
export function methodName(method: string) {
  return (
    (
      {
        auto: "Automatic",
        jenks: "Natural breaks",
        quantile: "Quantiles",
        equal_interval: "Equal interval",
        log_transform: "Logarithmic",
        log_jenks: "Logarithmic breaks",
        log_transform_then_jenks: "Logarithmic natural breaks",
        head_tail: "Head / tail breaks",
      } as Record<string, string>
    )[method] || method.replaceAll("_", " ")
  );
}
export async function api<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    ...(body === undefined
      ? {}
      : {
          method,
          headers: { "Content-Type": "application/json", "X-CartoLLM-Request": "1" },
          body: JSON.stringify(body),
        }),
    signal: AbortSignal.timeout(90000),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : `Request failed (${response.status}).`,
    );
  }
  return response.json();
}
