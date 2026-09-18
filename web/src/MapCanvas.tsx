import { useEffect, useRef, useState } from "react";
import maplibregl, {
  type Map as MapInstance,
  type StyleSpecification,
  type ExpressionSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { GeoData, MapPlan, County, ParkPlan, MapView } from "./types";
import type { LayerId } from "./layers";

export type Basemap = "light" | "dark" | "satellite";
export function basemapAttribution(
  basemap: Basemap,
  offline: boolean,
  html = false,
): string {
  if (offline) return "none";
  if (basemap === "satellite") {
    const esri = html ? '<a href="https://www.esri.com">Esri</a>' : "Esri";
    return `Tiles © ${esri} and imagery contributors`;
  }
  const osm = html
    ? '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    : "OpenStreetMap";
  return `Esri, HERE, Garmin, © ${osm} contributors, GIS user community`;
}

export const NJ_BOUNDS: [[number, number], [number, number]] = [
  [-75.58, 38.9],
  [-73.89, 41.36],
];

function mapStyle(basemap: Basemap, offline: boolean): StyleSpecification {
  const dark = basemap === "dark";
  const tiles =
    basemap === "satellite"
      ? [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ]
      : [
          `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${dark ? "Dark" : "Light"}_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
        ];
  return {
    version: 8,
    sources: offline
      ? {}
      : {
          basemap: {
            type: "raster",
            tiles,
            tileSize: 256,
            maxzoom: 16,
            attribution: basemapAttribution(basemap, offline, true),
          },
          labels: {
            type: "raster",
            tiles: [
              `https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_${dark ? "Dark" : "Light"}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
            ],
            tileSize: 256,
            maxzoom: 16,
          },
        },
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": dark ? "#252d32" : "#e9eee9" },
      },
      ...(!offline
        ? [
            {
              id: "basemap",
              type: "raster" as const,
              source: "basemap",
              paint: { "raster-opacity": 0.85 },
            },
          ]
        : []),
    ],
  };
}

export default function MapCanvas({
  counties,
  parksData,
  pointData,
  parkPoints,
  layerOrder,
  parkPlan,
  view,
  plan,
  parks,
  visible,
  opacity,
  outlines,
  basemap,
  offline,
  selected,
  onSelect,
  onReady,
  onViewChange,
}: {
  counties: GeoData;
  parksData: GeoData;
  pointData: GeoData;
  parkPoints: boolean;
  layerOrder: LayerId[];
  parkPlan: ParkPlan;
  view: MapView | null;
  plan: MapPlan;
  parks: boolean;
  visible: boolean;
  opacity: number;
  outlines: boolean;
  basemap: Basemap;
  offline: boolean;
  selected: County | null;
  onSelect: (county: County | null) => void;
  onReady: (map: MapInstance) => void;
  onViewChange: () => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<MapInstance | null>(null);
  const latest = useRef({
    counties, parksData, pointData, layerOrder,
    parkPoints,
    plan,
    parks,
    visible,
    opacity,
    outlines,
    selected,
    onSelect,
    onViewChange,
  });
  latest.current = {
    counties, parksData, pointData, layerOrder,
    parkPoints,
    plan,
    parks,
    visible,
    opacity,
    outlines,
    selected,
    onSelect,
    onViewChange,
  };
  const [mapError, setMapError] = useState("");
  const [tileError, setTileError] = useState(false);
  const camera = useRef<MapView | null>(view);
  const importedView = useRef(view);
  if (importedView.current !== view) {
    importedView.current = view;
    camera.current = view;
  }

  function paint(map: MapInstance) {
    if (!map.getLayer("county-fill")) return;
    const p = latest.current;
    // Gate 2 uses right-inclusive bins: a value exactly at an interior break
    // belongs to the lower class. Keep renderer and legend in agreement.
    const expression: unknown[] = ["case"];
    p.plan.breaks
      .slice(1, -1)
      .forEach((cut, i) =>
        expression.push(["<=", ["get", p.plan.metric], cut], p.plan.colors[i]),
      );
    expression.push(p.plan.colors.at(-1));
    map.setPaintProperty(
      "county-fill",
      "fill-color",
      expression as ExpressionSpecification,
    );
    map.setPaintProperty("county-fill", "fill-opacity", p.opacity / 100);
    map.setLayoutProperty(
      "county-fill",
      "visibility",
      p.visible ? "visible" : "none",
    );
    map.setLayoutProperty(
      "county-lines",
      "visibility",
      p.outlines && p.visible ? "visible" : "none",
    );
    map.setLayoutProperty(
      "park-fill",
      "visibility",
      p.parks ? "visible" : "none",
    );
    map.setLayoutProperty(
      "park-lines",
      "visibility",
      p.parks ? "visible" : "none",
    );
    map.setFilter("selected-county", [
      "==",
      ["get", "id"],
      p.selected?.id || "",
    ]);
    if (map.getLayer("park-points")) map.setLayoutProperty("park-points", "visibility", p.parkPoints ? "visible" : "none");
    const groups: Record<LayerId, string[]> = { counties: ["county-fill", "county-lines"], parks: ["park-fill", "park-lines"], park_points: ["park-points"] };
    for (const id of p.layerOrder) for (const layer of groups[id]) if (map.getLayer(layer)) map.moveLayer(layer);
    // Derived analysis stays above the base thematic stack after every style
    // change, rather than being covered by a newly reordered polygon layer.
    for (const id of ["p2-tract-fill", "p2-tract-line", "p2-matches", "p2-buffer-fill", "p2-buffer-line"]) if (map.getLayer(id)) map.moveLayer(id);
    for (const layer of map.getStyle().layers || []) if (layer.id.startsWith("p2-ref-")) map.moveLayer(layer.id);
    if (map.getLayer("p2-tract-fill") && map.getLayoutProperty("p2-tract-fill", "visibility") === "visible") map.moveLayer("park-points");
    if (map.getLayer("place-labels")) map.moveLayer("place-labels");
    map.moveLayer("selected-county");
  }

  useEffect(() => {
    if (!container.current) return;
    let map: MapInstance;
    try {
      map = new maplibregl.Map({
        container: container.current,
        style: mapStyle(basemap, offline),
        bounds: NJ_BOUNDS,
        fitBoundsOptions: { padding: 55 },
        minZoom: 5,
        maxZoom: 15,
        attributionControl: { compact: true },
        canvasContextAttributes: { preserveDrawingBuffer: true },
      });
      if (camera.current) map.jumpTo(camera.current);
    } catch {
      setMapError(
        "The map needs WebGL. Enable hardware acceleration in your browser and reload.",
      );
      return;
    }
    instance.current = map;
    map.on("moveend", () => {
      latest.current.onViewChange();
      const center = map.getCenter();
      camera.current = {
        center: [center.lng, center.lat],
        zoom: map.getZoom(),
        bearing: map.getBearing(),
        pitch: map.getPitch(),
        selected_county: null,
      };
    });
    map.addControl(
      new maplibregl.ScaleControl({ maxWidth: 90, unit: "imperial" }),
      "bottom-left",
    );
    const popup = new maplibregl.Popup({
      closeButton: true,
      maxWidth: "240px",
    });
    map.on("error", (event) => {
      if (
        event.error.message.includes("fetch") ||
        event.error.message.includes("AJAX")
      )
        setTileError(true);
    });
    map.on("style.load", () => {
      map.addSource("counties", { type: "geojson", data: latest.current.counties });
      map.addSource("parks", { type: "geojson", data: latest.current.parksData });
      map.addSource("park-points", { type: "geojson", data: latest.current.pointData });
      map.addLayer({
        id: "county-fill",
        type: "fill",
        source: "counties",
        paint: { "fill-color": "#80b696", "fill-opacity": 0.85 },
      });
      map.addLayer({
        id: "county-lines",
        type: "line",
        source: "counties",
        paint: {
          "line-color": basemap === "dark" ? "#d9e6de" : "#ffffff",
          "line-width": 1.4,
          "line-opacity": 0.95,
        },
      });
      map.addLayer({
        id: "selected-county",
        type: "line",
        source: "counties",
        paint: { "line-color": "#193e35", "line-width": 3 },
        filter: ["==", ["get", "id"], ""],
      });
      if (!offline && basemap !== "satellite")
        map.addLayer({ id: "place-labels", type: "raster", source: "labels" });
      map.addLayer({
        id: "park-fill",
        type: "fill",
        source: "parks",
        paint: {
          "fill-color": [
            "match",
            ["coalesce", ["get", "FEATURE_CLASS"], "__unspecified__"],
            ...parkPlan.categories.flatMap((c) => [c.value, c.color]),
            "#dedede",
          ] as unknown as ExpressionSpecification,
          "fill-opacity": 1,
        },
      });
      map.addLayer({
        id: "park-lines",
        type: "line",
        source: "parks",
        paint: { "line-color": "#193c34", "line-width": 0.8 },
      });
      map.addLayer({ id: "park-points", type: "circle", source: "park-points", paint: { "circle-radius": 5, "circle-color": "#c66b24", "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5 } });
      paint(map);
      onReady(map);
    });
    map.on("click", (event) => {
      const features = map.queryRenderedFeatures(event.point, {
        layers: ["park-points", "park-fill", "county-fill"],
      });
      if (features[0]?.layer.id === "park-points") {
        const content = document.createElement("div");
        const title = document.createElement("strong"); title.textContent = features[0].properties.name;
        const detail = document.createElement("p"); detail.textContent = "Historical GNIS 2016 park location. Public access not verified. Not a boundary or entrance.";
        content.append(title, detail); popup.setLngLat(event.lngLat).setDOMContent(content).addTo(map);
      } else if (features[0]?.layer.id === "park-fill") {
        const p = features[0].properties;
        const content = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = p.name;
        const detail = document.createElement("p");
        detail.textContent = `${p.USE_DESIGNATION || "Use unspecified"} · Public access: ${p.PUBLIC_ACCESS || "Not specified by NJDEP"}`;
        content.append(title, detail);
        if (p.FACILITY_URL) {
          try {
            const url = new URL(p.FACILITY_URL);
            if (["https:", "http:"].includes(url.protocol)) {
              const link = document.createElement("a");
              link.href = url.href;
              link.target = "_blank";
              link.rel = "noopener noreferrer";
              link.textContent = "Facility information and access rules";
              content.append(link);
            }
          } catch {
            /* Missing or malformed source links are not made clickable. */
          }
        }
        popup.setLngLat(event.lngLat).setDOMContent(content).addTo(map);
      } else {
        popup.remove();
        latest.current.onSelect((features[0]?.properties as County) || null);
      }
    });
    map.on("mousemove", (event) => {
      if (map.getLayer("park-fill"))
        map.getCanvas().style.cursor = map.queryRenderedFeatures(event.point, {
          layers: ["park-fill", "county-fill"],
        }).length
          ? "pointer"
          : "";
    });
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      popup.remove();
      map.remove();
      instance.current = null;
    };
  }, [basemap, offline]);

  useEffect(() => {
    if (view) instance.current?.jumpTo(view);
  }, [view]);

  useEffect(() => {
    if (instance.current) paint(instance.current);
  }, [plan, parks, parkPoints, layerOrder, visible, opacity, outlines, selected]);

  useEffect(() => {
    const map = instance.current;
    for (const [name, data] of [["counties", counties], ["parks", parksData], ["park-points", pointData]] as const) {
      const source = map?.getSource(name) as maplibregl.GeoJSONSource | undefined;
      source?.setData(data);
    }
  }, [counties, parksData, pointData]);

  return (
    <>
      <div
        ref={container}
        className="map-canvas"
        aria-label="Interactive New Jersey map"
      />
      {mapError && (
        <div className="map-error" role="alert">
          {mapError}
        </div>
      )}
      {tileError && !mapError && (
        <div className="tile-warning" role="status">
          Basemap unavailable. Loaded NJ data is still interactive.
        </div>
      )}
    </>
  );
}
