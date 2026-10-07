"use client";

// The map: county outlines from the US Census, towns for orientation, and every substation
// with projects waiting, coloured by realistic MW ahead. A substation without an exact
// position is never drawn as a guessed dot: it's counted on its county and listed there.

import "leaflet/dist/leaflet.css";
import type * as Leaflet from "leaflet";
import Link from "next/link";
import { addTransitionType, startTransition, useCallback, useEffect, useMemo, useRef, useState, ViewTransition } from "react";
import { api, type SiteSummary } from "@/shared/api";
import { CLASS_LABEL, classOf, classVar, mw, plural } from "@/shared/format";
import { Arrow, Back, Search } from "@/shared/icons";
import { TOWNS, type Town } from "@/shared/towns";
import { smoothMotion, travel, travelToBounds } from "./motion";

type Feature = { type: "Feature"; properties: Record<string, string>; geometry: Geometry };
type Geometry = { type: "Polygon"; coordinates: number[][][] } | { type: "MultiPolygon"; coordinates: number[][][][] };
type Collection = { type: "FeatureCollection"; features: Feature[] };

type Area = { kind: "county"; name: string; state: string } | { kind: "town"; name: string; lat: number; lon: number };
type View = { view: "welcome" } | { view: "area"; area: Area } | { view: "site"; site: string; area: Area | null };
type County = { name: string; state: string };

const CALIFORNIA: Leaflet.LatLngBoundsExpression = [
  [32.4, -124.5],
  [42, -114],
];
const RADIUS = [4.5, 6, 7.5, 9.5];
const NEAR_MILES = 60;
const START_TOWNS = ["Bakersfield", "Fresno", "Lancaster", "Palm Springs", "Blythe", "El Centro", "Los Banos", "Las Vegas"];
// Flying to a county stops short of filling the screen with it, so its neighbours still show.
const COUNTY_ZOOM = 9;

const onlyNew = (s: SiteSummary) => s.waiting_projects === 0 && s.new_rules_projects > 0;
const placed = (s: SiteSummary) => s.latitude != null && s.longitude != null;
// The operator sometimes names two counties ("Lake/Colusa"): listed under both.
const countiesOf = (s: SiteSummary) => (s.county ? s.county.split("/").map((c) => c.trim()) : []);
const countyKey = (name: string, state: string) => `${name}|${state}`;

const toRad = (d: number) => (d * Math.PI) / 180;
function miles(a: [number, number], b: [number, number]): number {
  const dLat = toRad(b[0] - a[0]);
  const dLon = toRad(b[1] - a[1]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLon / 2) ** 2;
  return 2 * 3958.8 * Math.asin(Math.sqrt(h));
}

// The part of the map the panel doesn't cover: beside it on a wide screen, above it on a
// phone, where the panel sits along the bottom. Flights aim for the middle of that part.
function uncovered(map: Leaflet.Map, pad = 0): { paddingTopLeft: [number, number]; paddingBottomRight: [number, number] } {
  const box = map.getContainer().getBoundingClientRect();
  const panel = map.getContainer().parentElement?.querySelector(".panel")?.getBoundingClientRect();
  if (!panel) return { paddingTopLeft: [pad, pad], paddingBottomRight: [pad, pad] };
  return panel.width < box.width * 0.6
    ? { paddingTopLeft: [panel.right - box.left + pad, pad], paddingBottomRight: [pad, pad] }
    : { paddingTopLeft: [pad, pad], paddingBottomRight: [pad, box.bottom - panel.top + pad] };
}

// Go so that `at` ends up in the middle of the uncovered part.
function goToPlace(map: Leaflet.Map, at: Leaflet.LatLngExpression, zoom: number) {
  const { paddingTopLeft: tl, paddingBottomRight: br } = uncovered(map);
  const shift = map.project(at, zoom).subtract([(tl[0] - br[0]) / 2, (tl[1] - br[1]) / 2]);
  travel(map, map.unproject(shift, zoom), zoom);
}

// The panel slides forward as you go deeper (a place, then a substation) and back as you
// return, so it's always clear which way you went.
const depth = (v: View) => ({ welcome: 0, area: 1, site: 2 })[v.view];
const SLIDE = { "panel-forward": "panel-forward", "panel-back": "panel-back", "panel-swap": "panel-swap", default: "none" };

export function MapApp() {
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [geo, setGeo] = useState<{ counties: Collection; states: Collection } | null>(null);
  const [view, setViewNow] = useState<View>({ view: "welcome" });
  const [q, setQ] = useState("");
  const [over, setOver] = useState<County | null>(null);
  const at = useRef(0);

  const setView = useCallback((next: View) => {
    const from = at.current;
    at.current = depth(next);
    startTransition(() => {
      addTransitionType(at.current > from ? "panel-forward" : at.current < from ? "panel-back" : "panel-swap");
      setViewNow(next);
    });
  }, []);

  useEffect(() => {
    api
      .sites()
      .then((s) =>
        startTransition(() => {
          addTransitionType("panel-swap");
          setSites(s.sites);
        }),
      )
      .catch((e: Error) => setFailed(e.message));
    Promise.all([fetch("/geo/counties.json"), fetch("/geo/states.json")])
      .then(async ([c, s]) => setGeo({ counties: (await c.json()) as Collection, states: (await s.json()) as Collection }))
      .catch((e: Error) => setFailed(e.message));
  }, []);

  const map = useLeafletMap(sites, geo, view, setView, setOver);

  const pickSite = useCallback(
    (name: string, area?: Area | null) => {
      const s = sites?.find((x) => x.site === name);
      if (!s) return;
      const state = s.state ?? "CA";
      const first = countiesOf(s)[0];
      setView({ view: "site", site: name, area: area ?? (first ? { kind: "county", name: first, state } : null) });
    },
    [sites, setView],
  );

  const perCounty = useMemo(() => {
    const n = new Map<string, number>();
    for (const s of sites ?? []) for (const c of countiesOf(s)) n.set(countyKey(c, s.state ?? "CA"), (n.get(countyKey(c, s.state ?? "CA")) ?? 0) + 1);
    return n;
  }, [sites]);

  const key = failed
    ? "failed"
    : !sites
      ? "loading"
      : view.view === "welcome"
        ? "welcome"
        : view.view === "area"
          ? `area:${view.area.name}`
          : `site:${view.site}`;
  const hovered = over ?? { name: "", state: "" };
  const hoveredN = perCounty.get(countyKey(hovered.name, hovered.state)) ?? 0;
  const area = view.view === "welcome" ? null : view.area;
  const showing = view.view === "area" && area?.kind === "county" && area.name === hovered.name && area.state === hovered.state;

  return (
    <div className="mapwrap">
      <div id="lmap" ref={map.el} aria-label="Map of substations" />
      <div className={`hoverchip${over ? " on" : ""}`} aria-hidden="true">
        <b>{hovered.name} County</b>
        <span>
          {!hoveredN
            ? "No substations with projects waiting"
            : showing
              ? `${plural(hoveredN, "substation")}, listed on the left`
              : `${plural(hoveredN, "substation")} · click to see them`}
        </span>
      </div>
      <aside className="panel" aria-label="Find a place">
        <ViewTransition key={key} enter={SLIDE} exit={SLIDE} default="none">
          <div className="pview">
            {failed ? (
              <div className="ph">
                <h1>Explore by place</h1>
                <p className="notice">The map couldn&apos;t load: {failed}</p>
              </div>
            ) : !sites ? (
              <div className="ph">
                <h1>Explore by place</h1>
                <p>Working out how crowded each substation is. The first visit takes a few seconds.</p>
                <div className="shimmer" aria-hidden="true" />
              </div>
            ) : view.view === "welcome" ? (
              <Welcome sites={sites} q={q} setQ={setQ} setView={setView} pickSite={pickSite} />
            ) : view.view === "area" ? (
              <AreaList sites={sites} area={view.area} setView={setView} pickSite={pickSite} light={map.light} />
            ) : (
              <SiteCard sites={sites} view={view} setView={setView} />
            )}
          </div>
        </ViewTransition>
      </aside>
      <Legend />
    </div>
  );
}

// --- The Leaflet map ---------------------------------------------------------------------

// A county's outline, kept to tell which county the pointer is over. Hovering goes by where
// the pointer is, not by which shape is under it, so it holds steady over dots and labels.
type Shape = { key: string; box: [number, number, number, number]; rings: number[][][] };

function shapeOf(key: string, g: Geometry): Shape {
  const rings = g.type === "Polygon" ? g.coordinates : g.coordinates.flat();
  const box: Shape["box"] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const r of rings)
    for (const [x, y] of r) {
      box[0] = Math.min(box[0], x);
      box[1] = Math.min(box[1], y);
      box[2] = Math.max(box[2], x);
      box[3] = Math.max(box[3], y);
    }
  return { key, box, rings };
}

function countyAt(shapes: Shape[], at: Leaflet.LatLng): string | null {
  const x = at.lng;
  const y = at.lat;
  for (const s of shapes) {
    if (x < s.box[0] || x > s.box[2] || y < s.box[1] || y > s.box[3]) continue;
    let inside = false;
    for (const r of s.rings)
      for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
        const [xi, yi] = r[i];
        const [xj, yj] = r[j];
        if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
      }
    if (inside) return s.key;
  }
  return null;
}

type Outlined = Leaflet.Path & { getBounds(): Leaflet.LatLngBounds };

function useLeafletMap(
  sites: SiteSummary[] | null,
  geo: { counties: Collection; states: Collection } | null,
  view: View,
  setView: (v: View) => void,
  onHover: (c: County | null) => void,
) {
  const el = useRef<HTMLDivElement | null>(null);
  const ref = useRef<{
    L: typeof Leaflet;
    map: Leaflet.Map;
    sites: Map<string, Leaflet.CircleMarker>;
    counties: Map<string, Outlined>;
    outlines: Map<string, Outlined>;
    picked: string | null;
    ring: { marker: Leaflet.CircleMarker; k: number } | null;
    size: () => number;
  } | null>(null);
  const [ready, setReady] = useState(0);

  useEffect(() => {
    if (!sites || !geo || !el.current || ref.current) return;
    let cancelled = false;
    void import("leaflet").then(({ default: L }) => {
      if (cancelled || !el.current) return;
      const map = L.map(el.current, {
        zoomControl: false,
        minZoom: 5,
        maxZoom: 11,
        zoomSnap: 0,
        zoomAnimation: false,
        markerZoomAnimation: false,
        fadeAnimation: false,
        scrollWheelZoom: false,
      });
      smoothMotion(map);
      // Highlighted borders sit on a layer of their own above every county, so a neighbour
      // never paints over them; the substations sit above both.
      map.createPane("outlines").style.zIndex = "410";
      // Names and county badges sit below the substations, so a dot is never hidden.
      map.createPane("labels").style.zIndex = "412";
      map.createPane("badges").style.zIndex = "415";
      // New-rules rings sit under every dot, so a small dot's ring never cuts across a
      // neighbour drawn close by.
      map.createPane("halos").style.zIndex = "418";
      map.createPane("sites").style.zIndex = "420";
      map.fitBounds(CALIFORNIA, uncovered(map));
      L.control.zoom({ position: "topright" }).addTo(map);
      map.attributionControl
        .setPrefix(false)
        .addAttribution(
          "Boundaries: US Census Bureau · Substation positions: © OpenStreetMap contributors and public filings",
        );
      // Borders drawn with every point, so they don't shimmer as the zoom changes.
      const exact = { smoothFactor: 0, interactive: false } as Leaflet.GeoJSONOptions;
      L.geoJSON(geo.states as never, {
        ...exact,
        style: (f) => ({ className: `state${f?.properties.code === "CA" ? " home" : ""}`, weight: 1 }),
      }).addTo(map);

      const counties = new Map<string, Outlined>();
      const outlines = new Map<string, Outlined>();
      const shapes: Shape[] = [];
      const labels: Leaflet.Marker[] = [];
      L.geoJSON(geo.counties as never, {
        ...exact,
        style: (f) => ({ className: `county ${f?.properties.state === "CA" ? "ca" : "other"}`, weight: 0.8 }),
        onEachFeature: (f, layer) => {
          const { name, state } = f.properties as { name: string; state: string };
          const path = layer as Outlined;
          counties.set(countyKey(name, state), path);
          shapes.push(shapeOf(countyKey(name, state), (f as unknown as Feature).geometry));
          labels.push(
            L.marker(path.getBounds().getCenter(), {
              pane: "labels",
              interactive: false,
              keyboard: false,
              icon: L.divIcon({
                className: "",
                html: `<div class="county-label" aria-hidden="true">${escape(name)}</div>`,
                iconSize: [120, 14],
                iconAnchor: [60, 7],
              }),
            }),
          );
        },
      }).addTo(map);
      L.geoJSON(geo.counties as never, {
        ...exact,
        pane: "outlines",
        style: () => ({ className: "outline", weight: 2 }),
        onEachFeature: (f, layer) => outlines.set(countyKey(f.properties.name, f.properties.state), layer as Outlined),
      }).addTo(map);
      for (const m of labels) m.addTo(map);

      // Unplaced substations: a badge in their county, never a guessed point.
      const unplacedIn = new Map<string, SiteSummary[]>();
      for (const s of sites.filter((x) => !placed(x))) {
        for (const c of countiesOf(s)) {
          const key = countyKey(c, s.state ?? "CA");
          unplacedIn.set(key, [...(unplacedIn.get(key) ?? []), s]);
        }
      }
      for (const [key, list] of unplacedIn) {
        const county = counties.get(key);
        if (!county) continue;
        const [name, state] = key.split("|");
        const n = list.length;
        L.marker(county.getBounds().getCenter(), {
          pane: "badges",
          icon: L.divIcon({
            className: "badge-icon",
            html: `<span class="cbadge" title="${n} substation${n > 1 ? "s" : ""} somewhere in ${escape(name)} County">+${n}</span>`,
            iconSize: [40, 20],
            iconAnchor: [20, 22],
          }),
        })
          .on("click", () => setView({ view: "area", area: { kind: "county", name, state } }))
          .bindTooltip(
            `${n} more substation${n > 1 ? "s" : ""} somewhere in ${escape(name)} County.<br><span class="dim">Their exact spot isn't known, so they aren't drawn as dots.</span>`,
            { direction: "top", offset: [0, -18] },
          )
          .addTo(map);
      }

      for (const [n, lat, lon, major] of TOWNS) {
        L.marker([lat, lon], {
          pane: "labels",
          interactive: false,
          keyboard: false,
          icon: L.divIcon({
            className: "",
            html: `<div class="city-label${major ? " major" : ""}" aria-hidden="true"><i></i>${escape(n)}</div>`,
            iconSize: [140, 16],
            iconAnchor: [2, 8],
          }),
        }).addTo(map);
      }

      // Substations, biggest first so small ones stay on top. They appear in a sweep from
      // west to east when the map first loads.
      const markers = new Map<string, Leaflet.CircleMarker>();
      const sized: [Leaflet.CircleMarker, number, number][] = [];
      for (const s of sites.filter(placed).sort((a, b) => b.realistic_mw - a.realistic_mw)) {
        const at: [number, number] = [s.latitude as number, s.longitude as number];
        const k = classOf(s.realistic_mw);
        const delay = `${Math.round(Math.min(Math.max((at[1] + 124.5) / 10.5, 0), 1) * 600)}ms`;
        if (s.new_rules_projects > 0 && !onlyNew(s)) {
          const halo = L.circleMarker(at, { pane: "halos", radius: 1, className: "halo", interactive: false }).addTo(map);
          (halo.getElement() as SVGElement | undefined)?.style.setProperty("--d", delay);
          sized.push([halo, k, 3.5]);
        }
        const marker = L.circleMarker(at, {
          pane: "sites",
          radius: 6,
          bubblingMouseEvents: false,
          className: `site k${k}${onlyNew(s) ? " onlynew" : ""}${s.positioned_by === "planned" ? " planned" : ""}`,
        })
          .bindTooltip(
            `<b>${escape(s.site)}</b><br>${
              onlyNew(s) ? "Only new-rules projects waiting" : `${mw(s.realistic_mw)} MW realistically ahead`
            }${s.positioned_by === "planned" ? `<br><span class="dim">Planned, not built yet</span>` : ""}`,
            { direction: "top", offset: [0, -6] },
          )
          .on("mouseover", () => toFront(marker))
          .on("click", () => {
            // The map is about to move out from under the pointer: don't carry the label along.
            marker.closeTooltip();
            const first = countiesOf(s)[0];
            setView({
              view: "site",
              site: s.site,
              area: first ? { kind: "county", name: first, state: s.state ?? "CA" } : null,
            });
          })
          .addTo(map);
        const path = marker.getElement() as SVGElement | undefined;
        path?.setAttribute("data-site", s.site);
        path?.setAttribute("aria-label", s.site);
        path?.style.setProperty("--d", delay);
        markers.set(s.site, marker);
        sized.push([marker, k, 0]);
      }

      // Dots grow a little as you zoom in, smoothly with the zoom itself; names fade in once
      // there's room for them.
      const size = () => Math.max(0.8, Math.min(1.6, 0.6 + (map.getZoom() - 5) * 0.25));
      const onZoom = () => {
        const z = map.getZoom();
        const f = size();
        for (const [m, k, extra] of sized) m.setRadius(RADIUS[k] * f + extra);
        const ring = ref.current?.ring;
        if (ring) ring.marker.setRadius(RADIUS[ring.k] * f + 5);
        const c = map.getContainer().classList;
        c.toggle("z-cities", z >= 5.5);
        c.toggle("z-towns", z >= 7);
        c.toggle("z-counties", z >= 7.75);
      };
      map.on("zoom", onZoom);
      onZoom();
      // Once the dots have swept in, stop their entrance so raising one doesn't replay it.
      setTimeout(() => map.getContainer().classList.add("settled"), 1600);

      // Hovering and picking a county.
      let hovered: string | null = null;
      const hover = (key: string | null) => {
        if (key === hovered) return;
        for (const k of [hovered, key]) {
          if (!k) continue;
          counties.get(k)?.getElement()?.classList.toggle("hover", k === key);
          outlines.get(k)?.getElement()?.classList.toggle("hover", k === key);
        }
        hovered = key;
        map.getContainer().classList.toggle("over-county", key != null);
        const [name, state] = key?.split("|") ?? [];
        onHover(key ? { name, state } : null);
      };
      // After a flight the map has moved under a still pointer: look again where it rests.
      let pointer: Leaflet.Point | null = null;
      map.on("mousemove", (e) => {
        pointer = e.containerPoint;
        hover(countyAt(shapes, e.latlng));
      });
      map.on("moveend", () => pointer && hover(countyAt(shapes, map.containerPointToLatLng(pointer))));
      map.getContainer().addEventListener("mouseleave", () => {
        pointer = null;
        hover(null);
      });
      map.on("click", (e) => {
        const key = countyAt(shapes, e.latlng);
        if (!key) return;
        const [name, state] = key.split("|");
        setView({ view: "area", area: { kind: "county", name, state } });
      });

      ref.current = { L, map, sites: markers, counties, outlines, picked: null, ring: null, size };
      setReady((n) => n + 1);
    });
    return () => {
      cancelled = true;
    };
  }, [sites, geo, setView, onHover]);

  useEffect(
    () => () => {
      ref.current?.map.remove();
      ref.current = null;
    },
    [],
  );

  // Follow the panel: fly to what was picked and highlight it.
  useEffect(() => {
    const m = ref.current;
    if (!m || !sites) return;
    const { L, map } = m;
    const pick = (a: Area | null) => {
      const key = a?.kind === "county" ? countyKey(a.name, a.state) : null;
      if (key === m.picked) return;
      for (const k of [m.picked, key]) {
        if (!k) continue;
        m.counties.get(k)?.getElement()?.classList.toggle("picked", k === key);
        m.outlines.get(k)?.getElement()?.classList.toggle("picked", k === key);
      }
      if (key) m.outlines.get(key)?.bringToFront();
      m.picked = key;
    };
    m.ring?.marker.remove();
    m.ring = null;
    if (view.view === "welcome") {
      pick(null);
      travelToBounds(map, CALIFORNIA, uncovered(map));
    } else if (view.view === "area") {
      pick(view.area);
      if (view.area.kind === "town") goToPlace(map, [view.area.lat, view.area.lon], 8.5);
      else {
        const c = m.counties.get(countyKey(view.area.name, view.area.state));
        if (c) travelToBounds(map, c.getBounds(), { ...uncovered(map, 30), maxZoom: COUNTY_ZOOM });
      }
    } else {
      const s = sites.find((x) => x.site === view.site);
      pick(view.area);
      if (s && placed(s)) {
        const at: [number, number] = [s.latitude as number, s.longitude as number];
        const k = classOf(s.realistic_mw);
        goToPlace(map, at, Math.max(map.getZoom(), 8.5));
        const marker = L.circleMarker(at, {
          pane: "sites",
          radius: RADIUS[k] * m.size() + 5,
          className: "sel-ring",
          interactive: false,
        }).addTo(map);
        m.ring = { marker, k };
        const dot = m.sites.get(s.site);
        if (dot) toFront(dot);
      } else if (view.area?.kind === "county") {
        const c = m.counties.get(countyKey(view.area.name, view.area.state));
        if (c) travelToBounds(map, c.getBounds(), { ...uncovered(map, 40), maxZoom: COUNTY_ZOOM });
      }
    }
  }, [view, sites, ready]);

  // A substation's dot lights up while its row in the panel is hovered.
  const light = useCallback((site: string | null) => {
    for (const [name, marker] of ref.current?.sites ?? []) {
      marker.getElement()?.classList.toggle("lit", name === site);
      if (name === site) toFront(marker);
    }
  }, []);

  return { el, light };
}

// Dots close together overlap; the one being hovered, lit or picked comes to the top.
function toFront(marker: Leaflet.CircleMarker) {
  const el = marker.getElement();
  if (el && el.parentNode?.lastChild !== el) marker.bringToFront();
}

function escape(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
}

// --- The panel -----------------------------------------------------------------------

function Welcome({
  sites,
  q,
  setQ,
  setView,
  pickSite,
}: {
  sites: SiteSummary[];
  q: string;
  setQ: (q: string) => void;
  setView: (v: View) => void;
  pickSite: (name: string) => void;
}) {
  const town = (t: Town) => setView({ view: "area", area: { kind: "town", name: t[0], lat: t[1], lon: t[2] } });
  return (
    <>
      <div className="ph">
        <h1>Explore by place</h1>
        <p>Type a town or county to see the substations around it, where new projects connect to the grid.</p>
        <SearchBox sites={sites} q={q} setQ={setQ} setView={setView} pickSite={pickSite} />
      </div>
      <div className="pb">
        <div className="sec">Or start from a town</div>
        <div className="chips" style={{ padding: "0 10px" }}>
          {START_TOWNS.map((name) => {
            const t = TOWNS.find((x) => x[0] === name) as Town;
            return (
              <button key={name} onClick={() => town(t)}>
                {name}
              </button>
            );
          })}
        </div>
        <div className="sec" style={{ marginTop: 12 }}>
          Reading the map
        </div>
        <div className="howto">
          <div>
            <b className="n">1</b>
            <span>
              Each circle is a <b>substation</b>, where power plants connect to the grid.
            </span>
          </div>
          <div>
            <b className="n">2</b>
            <span>
              <b>Darker and bigger</b> means more projects are realistically waiting there.
            </span>
          </div>
          <div>
            <b className="n">3</b>
            <span>Pick one to see how likely a new project is to be built there, and how long it tends to take.</span>
          </div>
        </div>
      </div>
    </>
  );
}

function SearchBox({
  sites,
  q,
  setQ,
  setView,
  pickSite,
}: {
  sites: SiteSummary[];
  q: string;
  setQ: (q: string) => void;
  setView: (v: View) => void;
  pickSite: (name: string) => void;
}) {
  const t = q.trim().toLowerCase();
  const results = useMemo(() => {
    if (t.length < 2) return null;
    const counties = new Map<string, { name: string; state: string; n: number }>();
    for (const s of sites)
      for (const c of countiesOf(s)) {
        const key = countyKey(c, s.state ?? "CA");
        const had = counties.get(key);
        counties.set(key, { name: c, state: s.state ?? "CA", n: (had?.n ?? 0) + 1 });
      }
    return {
      towns: TOWNS.filter((x) => x[0].toLowerCase().includes(t)).slice(0, 5),
      counties: [...counties.values()].filter((c) => c.name.toLowerCase().includes(t)).slice(0, 4),
      subs: sites.filter((s) => s.site.toLowerCase().includes(t)).slice(0, 5),
    };
  }, [t, sites]);
  const none = results && !results.towns.length && !results.counties.length && !results.subs.length;
  return (
    <div className="search">
      <Search />
      <input
        type="search"
        autoComplete="off"
        placeholder="Town, county or substation"
        value={q}
        aria-label="Search a town, county or substation"
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== "Enter" || !results) return;
          const town = results.towns[0];
          const county = results.counties[0];
          const sub = results.subs[0];
          if (town) setView({ view: "area", area: { kind: "town", name: town[0], lat: town[1], lon: town[2] } });
          else if (county) setView({ view: "area", area: { kind: "county", name: county.name, state: county.state } });
          else if (sub) pickSite(sub.site);
        }}
      />
      {results && (
        <div className="results">
          {none ? (
            <>
              <div className="grp">No matches</div>
              <p className="muted small" style={{ margin: 0, padding: "4px 14px 10px" }}>
                Try a nearby town or the county name.
              </p>
            </>
          ) : (
            <>
              {results.towns.length > 0 && <div className="grp">Towns</div>}
              {results.towns.map((x) => (
                <button
                  key={x[0]}
                  onClick={() => {
                    setQ("");
                    setView({ view: "area", area: { kind: "town", name: x[0], lat: x[1], lon: x[2] } });
                  }}
                >
                  {x[0]} <span>town</span>
                </button>
              ))}
              {results.counties.length > 0 && <div className="grp">Counties</div>}
              {results.counties.map((c) => (
                <button
                  key={countyKey(c.name, c.state)}
                  onClick={() => {
                    setQ("");
                    setView({ view: "area", area: { kind: "county", name: c.name, state: c.state } });
                  }}
                >
                  {c.name} County <span>{plural(c.n, "substation")}</span>
                </button>
              ))}
              {results.subs.length > 0 && <div className="grp">Substations</div>}
              {results.subs.map((s) => (
                <button
                  key={s.site}
                  onClick={() => {
                    setQ("");
                    pickSite(s.site);
                  }}
                >
                  {s.site} <span>{s.county ? `${s.county} County` : ""}</span>
                </button>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SiteRow({
  s,
  extra,
  max,
  onPick,
  light,
}: {
  s: SiteSummary;
  extra: string;
  max: number;
  onPick: () => void;
  light?: (site: string | null) => void;
}) {
  return (
    <button
      className="row"
      onClick={onPick}
      onMouseEnter={() => light?.(s.site)}
      onMouseLeave={() => light?.(null)}
      onFocus={() => light?.(s.site)}
      onBlur={() => light?.(null)}
    >
      <span className="nm">
        {s.site} <small>{extra}</small>
      </span>
      {onlyNew(s) ? (
        <span className="v muted">
          — <small>only new-rules projects</small>
        </span>
      ) : (
        <span className="v t">
          {mw(s.realistic_mw)} MW <small>ahead</small>
        </span>
      )}
      <svg className="bar" viewBox="0 0 100 8" preserveAspectRatio="none" width="100%" height="8" aria-hidden="true">
        <rect y="1" width="100" height="6" rx="3" fill="var(--soft)" />
        <rect
          y="1"
          width={Math.max((s.realistic_mw / max) * 100, s.realistic_mw > 0 ? 1.2 : 0)}
          height="6"
          rx="3"
          fill={classVar(classOf(s.realistic_mw))}
        />
      </svg>
    </button>
  );
}

function AreaList({
  sites,
  area,
  setView,
  pickSite,
  light,
}: {
  sites: SiteSummary[];
  area: Area;
  setView: (v: View) => void;
  pickSite: (name: string, area?: Area | null) => void;
  light: (site: string | null) => void;
}) {
  // Nothing stays lit once the list goes away.
  useEffect(() => () => light(null), [light]);
  const max = Math.max(...sites.map((s) => s.realistic_mw));
  let near: { s: SiteSummary; d?: number }[];
  let somewhere: SiteSummary[];
  let title: string;
  let sub: string;
  if (area.kind === "town") {
    near = sites
      .filter(placed)
      .map((s) => ({ s, d: miles([area.lat, area.lon], [s.latitude as number, s.longitude as number]) }))
      .filter((x) => x.d <= NEAR_MILES)
      .sort((a, b) => (a.d ?? 0) - (b.d ?? 0));
    const counties = new Set(near.flatMap((x) => countiesOf(x.s)));
    somewhere = sites.filter((s) => !placed(s) && countiesOf(s).some((c) => counties.has(c)));
    title = `Near ${area.name}`;
    sub = `${plural(near.length, "substation")} within ${NEAR_MILES} miles`;
  } else {
    const inCounty = (s: SiteSummary) => (s.state ?? "CA") === area.state && countiesOf(s).includes(area.name);
    near = sites
      .filter((s) => placed(s) && inCounty(s))
      .map((s) => ({ s }))
      .sort((a, b) => b.s.realistic_mw - a.s.realistic_mw);
    somewhere = sites.filter((s) => !placed(s) && inCounty(s));
    title = `${area.name} County`;
    sub = `${plural(near.length + somewhere.length, "substation")} with projects waiting`;
  }
  const calmest = near
    .filter((x) => !onlyNew(x.s))
    .sort((a, b) => a.s.realistic_mw - b.s.realistic_mw)[0];
  return (
    <>
      <div className="ph">
        <button className="link" onClick={() => setView({ view: "welcome" })}>
          <Back /> Search again
        </button>
        <div>
          <h2>{title}</h2>
          <p>
            {sub}
            {calmest && near.length > 2 ? (
              <>
                . The least crowded is <b>{calmest.s.site}</b>.
              </>
            ) : (
              "."
            )}
          </p>
        </div>
      </div>
      <div className="pb">
        {near.length > 0 ? (
          <section aria-labelledby="sec-near">
            <div className="sec" id="sec-near">
              {area.kind === "town" ? "Closest first" : "Busiest first"}
            </div>
            {near.map((x) => (
              <SiteRow
                key={x.s.site}
                s={x.s}
                max={max}
                extra={
                  x.d != null
                    ? `${Math.round(x.d)} miles away`
                    : x.s.positioned_by === "planned"
                      ? "planned substation"
                      : `${x.s.county} County`
                }
                onPick={() => pickSite(x.s.site, area)}
                light={light}
              />
            ))}
          </section>
        ) : (
          <p className="muted" style={{ padding: "0 10px" }}>
            No substations with projects waiting nearby.
          </p>
        )}
        {somewhere.length > 0 && (
          <section aria-labelledby="sec-somewhere">
            <div className="sec" id="sec-somewhere">
              Somewhere in the area, location not exact
            </div>
            {somewhere.map((s) => (
              <SiteRow key={s.site} s={s} max={max} extra={`${s.county} County`} onPick={() => pickSite(s.site, area)} />
            ))}
          </section>
        )}
      </div>
    </>
  );
}

function SiteCard({
  sites,
  view,
  setView,
}: {
  sites: SiteSummary[];
  view: Extract<View, { view: "site" }>;
  setView: (v: View) => void;
}) {
  const s = sites.find((x) => x.site === view.site) as SiteSummary;
  const counted = sites.filter((x) => !onlyNew(x));
  const busier = counted.filter((x) => x.realistic_mw < s.realistic_mw).length;
  const where = {
    openstreetmap: `${s.county ?? "Unknown"} County`,
    document: `${s.county} County · placed from a public filing`,
    planned: `${s.county} County · planned, not built yet`,
    county: s.county ? `Somewhere in ${s.county} County` : "County not given",
  }[s.positioned_by];
  return (
    <>
      <div className="ph">
        <button
          className="link"
          onClick={() => setView(view.area ? { view: "area", area: view.area } : { view: "welcome" })}
        >
          <Back /> {view.area ? (view.area.kind === "town" ? `Near ${view.area.name}` : `${view.area.name} County`) : "Search again"}
        </button>
        <div>
          <h2>{s.site}</h2>
          <p>{where}</p>
        </div>
      </div>
      <div className="pb">
        <div className="site-card">
          {onlyNew(s) ? (
            <p style={{ margin: 0 }}>
              Only projects that applied under the 2023 rules are waiting here. Nothing under those rules has finished
              yet, so nobody can say how many will be built.
            </p>
          ) : (
            <div>
              <div className="big t">{mw(s.realistic_mw)} MW</div>
              <p style={{ margin: "6px 0 0", color: "var(--ink-2)" }}>
                of projects are realistically ahead of a new one here. That&apos;s more than at{" "}
                {Math.round((busier / counted.length) * 100)}% of substations.
              </p>
            </div>
          )}
          {s.new_rules_mw > 0 && !onlyNew(s) && (
            <div className="pill lav" style={{ justifySelf: "start" }}>
              + {mw(s.new_rules_mw)} MW from new-rules projects, odds unknown
            </div>
          )}
          <Link className="btn p" href={`/substations/${encodeURIComponent(s.site)}`} transitionTypes={["page-forward"]}>
            See the odds here <Arrow />
          </Link>
        </div>
      </div>
    </>
  );
}

function Legend() {
  return (
    <div className="legend" aria-label="Legend">
      <span className="title">Projects realistically ahead</span>
      <div className="scale">
        {CLASS_LABEL.map((l, k) => (
          <span key={l}>
            <i style={{ background: classVar(k) }} />
            {l}
          </span>
        ))}
      </div>
      <div className="ends">
        <span>fewer</span>
        <span>MW</span>
        <span>more</span>
      </div>
      <div className="keys">
        <span>
          <svg width="16" height="16" aria-hidden="true">
            <circle cx="8" cy="8" r="5" fill="var(--panel)" stroke="var(--t3)" strokeWidth="2.6" />
          </svg>
          Planned substation, not built yet
        </span>
        <span>
          <svg width="18" height="18" aria-hidden="true">
            <circle cx="9" cy="9" r="7.4" fill="none" stroke="var(--lav)" strokeWidth="2.2" />
            <circle cx="9" cy="9" r="4.4" fill="var(--t3)" />
          </svg>
          New-rules projects also waiting
        </span>
        <span>
          <span className="cbadge" style={{ cursor: "default" }}>
            +3
          </span>
          More somewhere in this county (zoom in)
        </span>
      </div>
    </div>
  );
}
