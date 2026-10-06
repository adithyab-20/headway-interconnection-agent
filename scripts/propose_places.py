"""Offline: draft the reviewed place tables, for a person to approve.

Developer tool only, never imported by the product (it uses fuzzy matching and the network).
It reads the loaded database and the source files, and writes proposals to ``review/``:

  * ``spellings.csv``         spelling -> site and voltage (or a line's two end sites)
  * ``positions.csv``         site -> its OpenStreetMap substation, with a county check
  * ``bottleneck_names.csv``  bottleneck list name -> cost file name and a short name
  * ``upgrade_places.csv``    planned upgrade -> the places its name mentions

Every row has ``approve`` (pre-filled with the recommendation: yes / no) and ``confidence``
(sure / unsure) plus the evidence. A person reviews the unsure rows, then

    uv run python scripts/propose_places.py --apply

copies the approved rows into ``src/interconnection_agent/places/``.

Run after loading (``load_all``), with the database up:

    uv run python scripts/propose_places.py
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from interconnection_agent.db import connect  # noqa: E402
from interconnection_agent.places import TABLES, voltage_class  # noqa: E402
from interconnection_agent.places.sources import load_sources  # noqa: E402
from interconnection_agent.poi import normalize_station  # noqa: E402

REVIEW = ROOT / "review"
OSM = ROOT / "data" / "osm_substations_ca_nv_az.json"

_DESCRIPTORS = re.compile(
    r"\b(substations?|sub|switching station|switchyard|sw sta|sw station|sw|station|"
    r"bus(es)?|line|tap|circuit|ckt|kv|new|proposed|no\.?\s*\d+|#\s*\d+)\b"
)
_VOLTAGE = re.compile(r"(\d{2,3})\s*(?:/\s*\d{2,3}\s*)?kv")


UTILITY_TAGS = re.compile(r"\((?:pg&?e|pge|sce|sdg&?e|sdge|iid|vea|gwl|lspc|nv ?energy)\)")
COMMON_WORDS = {
    "bay",
    "lake",
    "valley",
    "river",
    "mesa",
    "hill",
    "park",
    "center",
    "central",
    "north",
    "south",
    "east",
    "west",
    "city",
    "creek",
    "springs",
    "ranch",
}


def clean_key(key: str) -> str:
    key = key.replace("\u2013", "-").replace("\u2014", "-")
    key = UTILITY_TAGS.sub(" ", key)
    key = re.sub(r"#\s*\d+", " ", key)
    return " ".join(key.split())


def tidy_site(text: str) -> str:
    text = re.sub(r"\d{2,3}\s*(/\s*\d{2,3}\s*)?kv", " ", text)
    text = _DESCRIPTORS.sub(" ", text)
    text = re.sub(r"[^a-z0-9 '&.]", " ", text)
    return " ".join(text.split()).title()


def parse(key: str) -> dict[str, str]:
    """Best guess at one spelling, with the reasons it might be wrong."""
    doubts = []
    key = clean_key(key)
    volts = [int(v) for v in _VOLTAGE.findall(key)]
    kv = voltage_class(volts[0]) if volts else None
    if not volts:
        doubts.append("no voltage")
    body = key
    if "(" in body:
        doubts.append("parentheses")
        body = re.sub(r"\(.*?\)", " ", body)
    if re.search(r"&|\band\b|,", body):
        doubts.append("several places named")
    stripped = re.sub(r"\d{2,3}\s*(/\s*\d{2,3}\s*)?kv", " ", body)
    parts = [tidy_site(p) for p in stripped.split("-") if tidy_site(p)]
    is_line = " line" in key or "tap" in key or len(parts) == 2
    if is_line and len(parts) != 2:
        doubts.append(f"line with {len(parts)} named ends")
    site = parts[0] if parts else tidy_site(body)
    if not site:
        doubts.append("no name")
    return {
        "kind": "line" if is_line and len(parts) == 2 else "substation",
        "site": site,
        "voltage_kv": str(kv or ""),
        "other_end_site": parts[1] if is_line and len(parts) == 2 else "",
        "doubts": "; ".join(doubts),
    }


def propose_spellings(conn) -> list[dict[str, str]]:  # type: ignore[no-untyped-def]
    raw = conn.execute(
        "SELECT raw_poi, count(*) FROM projects WHERE source = 'caiso_raw' AND raw_poi IS NOT NULL "
        "GROUP BY 1"
    ).fetchall()
    sources = load_sources(ROOT / "data")
    by_key: dict[str, dict[str, object]] = defaultdict(lambda: {"n": 0, "examples": set()})
    for text, n in raw:
        k = normalize_station(text)
        by_key[k]["n"] += n  # type: ignore[operator]
        by_key[k]["examples"].add(text)  # type: ignore[union-attr]
    for point in sources.behind:
        by_key[normalize_station(point)]["examples"].add(point)  # type: ignore[union-attr]

    rows = []
    for key, info in by_key.items():
        p = parse(key)
        rows.append(
            {
                "station_key": key,
                **p,
                "projects": str(info["n"]),
                "examples": " | ".join(sorted(info["examples"]))[:200],
            }
        )  # type: ignore[arg-type]

    # Sites spelled almost the same are probably one site: propose the commoner spelling.
    weight = Counter()
    for r in rows:
        weight[r["site"]] += int(r["projects"]) + 1
    names = sorted(weight, key=lambda s: -weight[s])
    canonical: dict[str, str] = {}
    for name in names:
        if name in canonical:
            continue
        canonical[name] = name
        for other, score, _ in process.extract(name, names, scorer=fuzz.ratio, limit=8):
            if other != name and other not in canonical and score >= 90:
                canonical[other] = name
    voltages: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r["voltage_kv"]:
            voltages[canonical.get(r["site"], r["site"])].add(r["voltage_kv"])
    for r in rows:
        site = canonical.get(r["site"], r["site"])
        if not r["voltage_kv"] and len(voltages[site]) == 1:
            r["voltage_kv"] = next(iter(voltages[site]))
            r["doubts"] = "; ".join(d for d in r["doubts"].split("; ") if d != "no voltage")
        for field in ("site", "other_end_site"):
            if r[field] and canonical.get(r[field], r[field]) != r[field]:
                r["doubts"] = "; ".join(
                    filter(None, [r["doubts"], f"merged '{r[field]}' into '{canonical[r[field]]}'"])
                )
                r[field] = canonical[r[field]]
        r["confidence"] = "unsure" if r["doubts"] else "sure"
        r["approve"] = "yes"
        d = r["doubts"]
        if "line with 1 named ends" in d:
            r["kind"], r["other_end_site"] = "substation", ""  # a line named after one place
        if re.search(r"line with [3-9] named ends", d):
            ends = [
                tidy_site(x)
                for x in re.sub(r"\d{2,3}\s*kv", " ", clean_key(r["station_key"])).split("-")
                if tidy_site(x)
            ]
            r["kind"], r["site"], r["other_end_site"] = "line", ends[0], ends[-1]
        if "several places named" in d or "no name" in d or r["site"].lower().startswith("tbd"):
            r["approve"] = "no"  # left unplaced and reported
    by_site_volts: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        if r["voltage_kv"]:
            by_site_volts[r["site"]][r["voltage_kv"]] += int(r["projects"]) + 1
    for r in rows:
        if not r["voltage_kv"] and by_site_volts[r["site"]]:
            r["voltage_kv"] = by_site_volts[r["site"]].most_common(1)[0][0]
            r["doubts"] += "; voltage set to the site's most common"
    return sorted(rows, key=lambda r: (r["confidence"] != "unsure", r["site"]))


def county_of(lat: float, lon: float) -> str:
    url = (
        "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
        f"?x={lon}&y={lat}&benchmark=Public_AR_Current&vintage=Current_Current"
        "&layers=Counties&format=json"
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - fixed public API
            counties = json.load(resp)["result"]["geographies"].get("Counties", [])
        return counties[0]["BASENAME"] if counties else ""
    except (OSError, KeyError, ValueError):
        return ""


def propose_positions(conn, spellings: list[dict[str, str]]) -> list[dict[str, str]]:  # type: ignore[no-untyped-def]
    """Draft a position for every site, in the shape of the committed table, so the draft can
    be compared against it row by row. A position outside the projects' own county is always
    left for the reviewer: a neighbouring county is fine, the other side of the state is not.
    Positions read off public documents are added by hand, never drafted."""
    osm = json.loads(OSM.read_text())
    stamp = osm["osm3s"]["timestamp_osm_base"][:10]
    named: dict[str, list[dict[str, object]]] = defaultdict(list)
    for e in osm["elements"]:
        name = e.get("tags", {}).get("name")
        if name:
            named[tidy_site(normalize_station(name))].append(e)
    site_of = {r["station_key"]: (r["site"], r["other_end_site"]) for r in spellings}
    counties: dict[str, Counter[str]] = defaultdict(Counter)
    for raw, county in conn.execute(
        "SELECT raw_poi, county FROM projects WHERE source = 'caiso_raw' AND county IS NOT NULL"
    ).fetchall():
        for site in site_of.get(normalize_station(raw), ()):
            if site:
                counties[site][str(county).strip().title().removesuffix(" County")] += 1
    sites = sorted({r["site"] for r in spellings} | {r["other_end_site"] for r in spellings} - {""})
    rows = []
    for site in sites:
        ours = counties[site].most_common(1)[0][0] if counties[site] else ""
        candidates = named.get(site, [])
        drafted = _from_openstreetmap(site, candidates, ours, stamp) if candidates else None
        if drafted:
            rows.append(drafted)
    return sorted(rows, key=lambda r: (r["confidence"] != "unsure", r["site"]))


def _row(site: str, by: str, lat: str, lon: str, source: str, doubts: list[str], **rest: str):  # type: ignore[no-untyped-def]
    return {
        "site": site,
        "positioned_by": by,
        "latitude": lat,
        "longitude": lon,
        "source": source,
        "osm_id": "",
        "osm_name": "",
        **rest,
        "doubts": "; ".join(doubts),
        "confidence": "unsure" if doubts else "sure",
        "approve": "no" if doubts else "yes",
    }


def _from_openstreetmap(  # type: ignore[no-untyped-def]
    site: str, candidates: list[dict[str, object]], ours: str, stamp: str
):
    located = []
    for cand in candidates[:6]:
        lat = cand.get("lat") or cand.get("center", {}).get("lat")  # type: ignore[union-attr]
        lon = cand.get("lon") or cand.get("center", {}).get("lon")  # type: ignore[union-attr]
        located.append((cand, lat, lon, county_of(lat, lon).removesuffix(" County")))  # type: ignore[arg-type]
    same = [c for c in located if ours and c[3].lower() == ours.lower()]
    e, lat, lon, point_county = (same or located)[0]
    doubts = []
    if len(candidates) > 1:
        doubts.append(f"{len(candidates)} OpenStreetMap substations share this name")
    if ours and point_county and ours.lower() != point_county.lower():
        doubts.append(f"OpenStreetMap county {point_county}, projects say {ours}")
    osm_id = f"{e['type']}/{e['id']}"
    return _row(
        site,
        "openstreetmap",
        str(lat),
        str(lon),
        f"OpenStreetMap {osm_id}, data of {stamp}",
        doubts,
        osm_id=osm_id,
        osm_name=str(e["tags"]["name"]),  # type: ignore[index]
        point_county=point_county,
        project_county=ours,
    )


def propose_bottleneck_names() -> list[dict[str, str]]:
    sources = load_sources(ROOT / "data")
    cost_names = list(sources.cost_to_add_room)
    rows = []

    def short(name: str) -> str:
        name = clean_key(name.lower())
        name = re.sub(r"\b(area|deliverability|constraint|interconnection)\b", " ", name)
        name = re.sub(r"\s*-\s*", "-", name)
        return " ".join(name.split())

    shorts = {short(c): c for c in cost_names}
    for listed in sorted(sources.room_left_mw):
        mine = short(listed)
        best = process.extractOne(mine, list(shorts), scorer=fuzz.ratio)
        score = best[1] if best else 0
        match = shorts[best[0]] if best and score >= 85 else ""
        rows.append(
            {
                "bottleneck_list_name": listed,
                "cost_file_name": match,
                "bottleneck": re.sub(
                    r"\s*(area\s*)?(deliverability\s*)?constraint\s*$", "", listed, flags=re.I
                ).strip(),
                "best_cost_file_candidate": shorts[best[0]] if best else "",
                "score": str(round(score)),
                "confidence": "sure" if score >= 95 or score < 70 else "unsure",
                "approve": "yes",  # an empty cost_file_name means: no cost estimate for it
            }
        )
    return rows


def propose_upgrade_places(spellings: list[dict[str, str]]) -> list[dict[str, str]]:
    sources = load_sources(ROOT / "data")
    places = {(r["site"], r["voltage_kv"]) for r in spellings if r["kind"] == "substation"}
    by_site: dict[str, set[str]] = defaultdict(set)
    for site, kv in places:
        by_site[site].add(kv)
    rows = []
    for u in sources.upgrades:
        name = u.name
        volts = {
            str(voltage_class(int(v))) for v in re.findall(r"(\d{2,3})(?=\s*(?:/\d+)?\s*kV)", name)
        }
        for site, kvs in by_site.items():
            if len(site) < 4 or not re.search(rf"\b{re.escape(site)}\b", name, re.I):
                continue
            for kv in sorted(kvs & volts) or []:
                rows.append(
                    {
                        "plan_id": u.plan_id,
                        "upgrade": name,
                        "site": site,
                        "voltage_kv": kv,
                        "finish_year": str(u.expected_finish_year or ""),
                        "confidence": "unsure" if site.lower() in COMMON_WORDS else "sure",
                        "approve": "no"
                        if site.lower() in COMMON_WORDS
                        and not name.lower().startswith(site.lower())
                        else "yes",
                    }
                )
    return sorted(rows, key=lambda r: (r["confidence"] != "unsure", r["site"]))


def write(name: str, rows: list[dict[str, str]]) -> None:
    REVIEW.mkdir(exist_ok=True)
    with (REVIEW / name).open("w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    unsure = sum(1 for r in rows if r.get("confidence") == "unsure")
    print(f"review/{name}: {len(rows)} rows, {unsure} unsure")


KEEP = {
    "spellings.csv": ["station_key", "kind", "site", "voltage_kv", "other_end_site"],
    # positions.csv is no longer drafted here: it now also holds federal-dataset and
    # document positions, reviewed by hand (see places/README.md).
    "bottleneck_names.csv": ["bottleneck_list_name", "cost_file_name", "bottleneck"],
    "upgrade_places.csv": ["plan_id", "site", "voltage_kv"],
}


def apply() -> None:
    for name, fields in KEEP.items():  # review/positions.csv is for reference only
        with (REVIEW / name).open(newline="") as f:
            approved = [r for r in csv.DictReader(f) if r["approve"].strip().lower() == "yes"]
        with (TABLES / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(approved)
        print(f"{name}: {len(approved)} approved rows written")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    if parser.parse_args().apply:
        apply()
        return
    with connect() as conn:
        spellings = propose_spellings(conn)
        write("spellings.csv", spellings)
        write("positions.csv", propose_positions(conn, spellings))
    write("bottleneck_names.csv", propose_bottleneck_names())
    write("upgrade_places.csv", propose_upgrade_places(spellings))


if __name__ == "__main__":
    main()
