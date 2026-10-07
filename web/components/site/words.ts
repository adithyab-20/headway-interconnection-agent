// Plain words for the API's names: comparison groups, ladder steps, project types.

import type { Rung, Waiting } from "@/shared/api";

const TYPE_WORDS: Record<string, string> = {
  "Solar only": "solar-only projects",
  "Solar + battery": "solar + battery projects",
  "Battery only": "battery-only projects",
  Wind: "wind projects",
  Gas: "gas projects",
  "All projects": "projects",
};

/** "Solar + battery, 150-300 MW, across California" -> "solar + battery projects of 150–300
 * MW across California". */
export function plainGroup(description: string): string {
  const parts = description.split(", ");
  const kind = TYPE_WORDS[parts[0]] ?? parts[0].toLowerCase();
  const size = parts.find((p, i) => i > 0 && /MW/.test(p));
  const where = parts[parts.length - 1];
  return `${kind}${size ? ` of ${size.replace("-", "–")}` : ""} ${where}`;
}

/** The type and size part of a group's description: "Solar + battery, 150–300 MW". */
export function groupKind(description: string): string {
  return description.split(", ").slice(0, -1).join(", ").replace("-", "–");
}

/** A ladder step's short name, from the place outwards. */
export function rungLabel(r: Rung, site: string): string {
  switch (r.area_kind) {
    case "voltage section":
      return `${r.area} only`;
    case "site":
      return `All of ${site}`;
    case "bottleneck area":
      return `Behind ${r.area}`;
    case "county":
      return `${r.area} County`;
    default:
      return `Across California · ${groupKind(r.description)}`;
  }
}

export function typeName(p: Pick<Waiting, "types" | "type">): string {
  if (p.type === "Solar + battery") return "solar + battery";
  if (p.type) return { "Solar only": "solar", "Battery only": "battery", Wind: "wind", Gas: "gas" }[p.type] ?? p.type;
  return p.types.map((t) => ({ "Wind Turbine": "wind", "Natural Gas": "gas" })[t] ?? t.toLowerCase()).join(" + ") || "project";
}

export function stepWords(step: string | null): string {
  return (
    {
      "Agreement signed": "has signed its agreement",
      "Second study done": "finished its second study",
      "First study done": "finished its first study",
    }[step ?? ""] ?? "hasn't been studied yet"
  );
}
