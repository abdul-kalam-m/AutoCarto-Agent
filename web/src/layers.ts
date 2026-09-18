import type { County, GeoData } from "./types";

export type LayerId = "counties" | "parks" | "park_points";
export const DEFAULT_LAYER_ORDER: LayerId[] = ["counties", "parks", "park_points"];
export const LAYER_NAMES: Record<LayerId, string> = {
  counties: "County demographics", parks: "State-owned open space", park_points: "Historical park locations",
};

// Attribute selection, not geometric clipping. Multi-county features retain
// their complete source geometry if any named county matches.
export function filterCollection(data: GeoData, ids: string[], counties: County[], countyLayer = false): GeoData {
  if (!ids.length) return data;
  const names = counties.filter(c => ids.includes(c.id)).map(c => c.name.toLowerCase());
  return { ...data, features: data.features.filter(feature => {
    if (countyLayer) return ids.includes(String(feature.properties?.id));
    const value = String(feature.properties?.county || "").toLowerCase();
    return names.some(name => new RegExp(`(^|[^a-z])${name}([^a-z]|$)`).test(value));
  }) };
}
