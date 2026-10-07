"use client";

// The map: county outlines from the US Census, towns for orientation, and every substation
// with projects waiting, coloured by realistic MW ahead. A substation without an exact
// position is never drawn as a guessed dot: it's counted on its county and listed there.

import "leaflet/dist/leaflet.css";
import type * as Leaflet from "leaflet";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type SiteSummary } from "@/shared/api";
import { CLASS_LABEL, classOf, classVar, mw, plural } from "@/shared/format";
import { Arrow, Back, Search } from "@/shared/icons";
import { TOWNS, type Town } from "@/shared/towns";

type Feature = { type: "Feature"; properties: Record<string, string>; geometry: unknown };
type Collection = { type: "FeatureCollection"; features: Feature[] };

type Area = { kind: "county"; name: string; state: string } | { kind: "town"; name: string; lat: number; lon: number };
type View = { view: "welcome" } | { view: "area"; area: Area } | { view: "site"; site: string; area: Area | null };

const CALIFORNIA: Leaflet.LatLngBoundsExpression = [
  [32.4, -124.5],
  [42, -114],
];
const RADIUS = [4.5, 6, 7.5, 9.5];
const NEAR_MILES = 60;
const START_TOWNS = ["Bakersfield", "Fresno", "Lancaster", "Palm Springs", "Blythe", "El Centro", "Los Banos", "Las Vegas"];

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

const panelPadding = (): Leaflet.PointExpression => [typeof innerWidth !== "undefined" && innerWidth > 760 ? 400 : 0, 0];

export function MapApp() {
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [geo, setGeo] = useState<{ counties: Collection; states: Collection } | null>(null);
  const [view, setView] = useState<View>({ view: "welcome" });
  const [q, setQ] = useState("");

  useEffect(() => {
    api
      .sites()
      .then((s) => setSites(s.sites))
      .catch((e: Error) => setFailed(e.message));
    Promise.all([fetch("/geo/counties.json"), fetch("/geo/states.json")])
      .then(async ([c, s]) => setGeo({ counties: (await c.json()) as Collection, states: (await s.json()) as Collection }))
      .catch((e: Error) => setFailed(e.message));
  }, []);

  const map = useLeafletMap(sites, geo, view, setView);

  const pickSite = useCallback(
    (name: string, area?: Area | null) => {
      const s = sites?.find((x) => x.site === name);
      if (!s) return;
      const state = s.state ?? "CA";
      const first = countiesOf(s)[0];
      setView({ view: "site", site: name, area: area ?? (first ? { kind: "county", name: first, state } : null) });
    },
    [sites],
  );

  return (
    <div className="mapwrap">
      <div id="lmap" ref={map} aria-label="Map of substations" />
      <aside className="panel" aria-label="Find a place">
        {failed ? (
          <div className="ph">
            <h1>Explore by place</h1>
            <p className="notice">The map couldn&apos;t load: {failed}</p>
          </div>
        ) : !sites ? (
          <div className="ph">
            <h1>Explore by place</h1>
            <p>Working out how crowded each substation is. The first visit takes a few seconds.</p>
          </div>
        ) : view.view === "welcome" ? (
          <Welcome sites={sites} q={q} setQ={setQ} setView={setView} pickSite={pickSite} />
        ) : view.view === "area" ? (
          <AreaList sites={sites} area={view.area} setView={setView} pickSite={pickSite} />
        ) : (
          <SiteCard sites={sites} view={view} setView={setView} />
        )}
      </aside>
      <Legend />
    </div>
  );
}

// --- The Leaflet map ---------------------------------------------------------------------

function useLeafletMap(
  sites: SiteSummary[] | null,
  geo: { counties: Collection; states: Collection } | null,
  view: View,
  setView: (v: View) => void,
) {
  const el = useRef<HTMLDivElement | null>(null);
  const ref = useRef<{
    L: typeof Leaflet;
    map: Leaflet.Map;
    sites: Map<string, Leaflet.CircleMarker>;
    counties: Map<string, Leaflet.Path & { getBounds(): Leaflet.LatLngBounds }>;
    ring: Leaflet.CircleMarker | null;
  } | null>(null);
  const [ready, setReady] = useState(0);

  useEffect(() => {
    if (!sites || !geo || !el.current || ref.current) return;
    let cancelled = false;
    void import("leaflet").then(({ default: L }) => {
      if (cancelled || !el.current) return;
      const map = L.map(el.current, { zoomControl: false, minZoom: 5, maxZoom: 11, zoomSnap: 0.25 });
      map.fitBounds(CALIFORNIA, { paddingTopLeft: panelPadding() });
      L.control.zoom({ position: "topright" }).addTo(map);
      map.attributionControl
        .setPrefix(false)
        .addAttribution(
          "Boundaries: US Census Bureau · Substation positions: © OpenStreetMap contributors and public filings",
        );
      L.geoJSON(geo.states as never, {
        style: (f) => ({ className: `state${f?.properties.code === "CA" ? " home" : ""}`, weight: 1 }),
        interactive: false,
      }).addTo(map);

      const counties = new Map<string, Leaflet.Path & { getBounds(): Leaflet.LatLngBounds }>();
      const labels: Leaflet.Marker[] = [];
      L.geoJSON(geo.counties as never, {
        style: (f) => ({ className: `county ${f?.properties.state === "CA" ? "ca" : "other"}`, weight: 0.8 }),
        onEachFeature: (f, layer) => {
          const { name, state } = f.properties as { name: string; state: string };
          const path = layer as Leaflet.Path & { getBounds(): Leaflet.LatLngBounds };
          counties.set(countyKey(name, state), path);
          layer.on("click", () => setView({ view: "area", area: { kind: "county", name, state } }));
          labels.push(
            L.marker(path.getBounds().getCenter(), {
              interactive: false,
              icon: L.divIcon({
                className: "",
                html: `<div class="county-label">${escape(name)}</div>`,
                iconSize: [120, 14],
                iconAnchor: [60, 7],
              }),
            }),
          );
        },
      }).addTo(map);

      // Unplaced substations: a badge in their county, never a guessed point.
      const unplacedIn = new Map<string, SiteSummary[]>();
      for (const s of sites.filter((x) => !placed(x))) {
        for (const c of countiesOf(s)) {
          const key = countyKey(c, s.state ?? "CA");
          unplacedIn.set(key, [...(unplacedIn.get(key) ?? []), s]);
        }
      }
      const badges: Leaflet.Marker[] = [];
      for (const [key, list] of unplacedIn) {
        const county = counties.get(key);
        if (!county) continue;
        const [name, state] = key.split("|");
        const n = list.length;
        badges.push(
          L.marker(county.getBounds().getCenter(), {
            icon: L.divIcon({
              className: "",
              html: `<span class="cbadge" title="${n} substation${n > 1 ? "s" : ""} somewhere in ${escape(name)} County">+${n}</span>`,
              iconSize: [40, 20],
              iconAnchor: [20, 22],
            }),
          })
            .on("click", () => setView({ view: "area", area: { kind: "county", name, state } }))
            .bindTooltip(
              `${n} more substation${n > 1 ? "s" : ""} somewhere in ${escape(name)} County.<br><span class="dim">Their exact spot isn't known, so they aren't drawn as dots.</span>`,
              { direction: "top", offset: [0, -18] },
            ),
        );
      }

      const towns = TOWNS.map(
        ([n, lat, lon, major]) =>
          [
            major,
            L.marker([lat, lon], {
              interactive: false,
              icon: L.divIcon({
                className: "",
                html: `<div class="city-label${major ? " major" : ""}"><i></i>${escape(n)}</div>`,
                iconSize: [140, 16],
                iconAnchor: [2, 8],
              }),
            }),
          ] as const,
      );

      // Substations, biggest first so small ones stay on top.
      const markers = new Map<string, Leaflet.CircleMarker>();
      const halos: [Leaflet.CircleMarker, SiteSummary][] = [];
      for (const s of sites.filter(placed).sort((a, b) => b.realistic_mw - a.realistic_mw)) {
        const at: [number, number] = [s.latitude as number, s.longitude as number];
        if (s.new_rules_projects > 0 && !onlyNew(s)) {
          halos.push([L.circleMarker(at, { radius: 1, className: "halo", interactive: false }).addTo(map), s]);
        }
        const k = classOf(s.realistic_mw);
        const marker = L.circleMarker(at, {
          radius: 6,
          className: `site k${k}${onlyNew(s) ? " onlynew" : ""}${s.positioned_by === "planned" ? " planned" : ""}`,
        })
          .bindTooltip(
            `<b>${escape(s.site)}</b><br>${
              onlyNew(s) ? "Only new-rules projects waiting" : `${mw(s.realistic_mw)} MW realistically ahead`
            }${s.positioned_by === "planned" ? `<br><span class="dim">Planned, not built yet</span>` : ""}`,
            { direction: "top", offset: [0, -6] },
          )
          .on("click", () => {
            const first = countiesOf(s)[0];
            setView({
              view: "site",
              site: s.site,
              area: first ? { kind: "county", name: first, state: s.state ?? "CA" } : null,
            });
          })
          .addTo(map);
        const path = marker.getElement();
        path?.setAttribute("data-site", s.site);
        path?.setAttribute("aria-label", s.site);
        markers.set(s.site, marker);
      }

      const sizeForZoom = () => {
        const z = map.getZoom();
        const f = Math.max(0.8, Math.min(1.6, 0.6 + (z - 5) * 0.25));
        for (const [name, m] of markers) {
          const s = sites.find((x) => x.site === name);
          if (s) m.setRadius(RADIUS[classOf(s.realistic_mw)] * f);
        }
        for (const [h, s] of halos) h.setRadius(RADIUS[classOf(s.realistic_mw)] * f + 3.5);
        for (const [major, m] of towns) (major ? z >= 5.5 : z >= 7) ? m.addTo(map) : m.remove();
        for (const m of labels) (z >= 7.75 ? m.addTo(map) : m.remove());
        for (const m of badges) (z >= 7 ? m.addTo(map) : m.remove());
      };
      map.on("zoomend", sizeForZoom);
      sizeForZoom();
      ref.current = { L, map, sites: markers, counties, ring: null };
      setReady((n) => n + 1);
    });
    return () => {
      cancelled = true;
    };
  }, [sites, geo, setView]);

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
    for (const c of m.counties.values()) c.getElement()?.classList.remove("picked");
    m.ring?.remove();
    m.ring = null;
    const pick = (a: Area | null) => {
      if (a?.kind === "county") m.counties.get(countyKey(a.name, a.state))?.getElement()?.classList.add("picked");
    };
    if (view.view === "welcome") {
      map.flyToBounds(CALIFORNIA, { paddingTopLeft: panelPadding(), duration: 0.6 });
    } else if (view.view === "area") {
      pick(view.area);
      if (view.area.kind === "town") map.flyTo([view.area.lat, view.area.lon], 8.5, { duration: 0.7 });
      else {
        const c = m.counties.get(countyKey(view.area.name, view.area.state));
        if (c) map.flyToBounds(c.getBounds(), { paddingTopLeft: panelPadding(), padding: [30, 30], duration: 0.7 });
      }
    } else {
      const s = sites.find((x) => x.site === view.site);
      pick(view.area);
      if (s && placed(s)) {
        const at: [number, number] = [s.latitude as number, s.longitude as number];
        map.flyTo(at, Math.max(map.getZoom(), 8.5), { duration: 0.7 });
        m.ring = L.circleMarker(at, { radius: RADIUS[classOf(s.realistic_mw)] * 1.6 + 6, className: "sel-ring", interactive: false }).addTo(map);
      } else if (view.area?.kind === "county") {
        const c = m.counties.get(countyKey(view.area.name, view.area.state));
        if (c) map.flyToBounds(c.getBounds(), { padding: [40, 40], duration: 0.7 });
      }
    }
  }, [view, sites, ready]);

  return el;
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

function SiteRow({ s, extra, max, onPick }: { s: SiteSummary; extra: string; max: number; onPick: () => void }) {
  return (
    <button className="row" onClick={onPick}>
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
}: {
  sites: SiteSummary[];
  area: Area;
  setView: (v: View) => void;
  pickSite: (name: string, area?: Area | null) => void;
}) {
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
          <Link className="btn p" href={`/substations/${encodeURIComponent(s.site)}`}>
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
