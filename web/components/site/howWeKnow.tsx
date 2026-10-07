// What each of the page's own numbers means, and the rows it was worked out from.

import type { HowWeKnow } from "@/components/Drawer";
import { known, type Odds, type Row, type SiteDetail } from "@/shared/api";
import { in100, mw, pct, yrs } from "@/shared/format";
import { plainGroup } from "./words";

export function chanceAbout(odds: Odds, n: number, asOf: string): HowWeKnow | null {
  const o = odds.by_years[String(n)];
  if (!known(o)) return null;
  return {
    title: `${in100(o.chance)} in 100 built within ${n} years`,
    say: (
      <>
        We looked at <b>{o.projects} past {plainGroup(odds.used)}</b>. We followed each one from the day it applied:
        built, withdrew, or still waiting. A project still waiting only counts for the years we&apos;ve seen it, never
        as a failure. Then we redrew the group at random 400 times to get the likely range, {in100(o.range[0])} to{" "}
        {in100(o.range[1])} in 100.
      </>
    ),
    tally: [
      [o.built, "built"],
      [o.withdrawn, "withdrew"],
      [o.waiting, "still waiting"],
    ],
    kind: "worked out",
    asOf,
    rows: odds.rows,
  };
}

export function waitAbout(odds: Odds, n: number, asOf: string): HowWeKnow | null {
  const o = odds.by_years[String(n)];
  if (!known(o) || o.typical_wait == null) return null;
  return {
    title: `About ${Math.round(o.typical_wait)} years to get built`,
    say: (
      <>
        Of the {o.projects} similar projects, {o.built} were built. Half of those that get built had done so{" "}
        {yrs(o.typical_wait)} years after applying. It only counts projects that were built, so it looks better than
        waiting does. The likely range comes from redrawing the group at random 400 times.
      </>
    ),
    tally: [
      [o.built, "built"],
      [o.withdrawn, "withdrew"],
      [o.waiting, "still waiting"],
    ],
    kind: "worked out",
    asOf,
    rows: odds.rows,
  };
}

function rowsOf(detail: SiteDetail, ids: string[]): Row[] {
  const by = new Map(detail.projects.map((p) => [p.id, p]));
  return ids.map((id) => by.get(id)).filter((r): r is Row => !!r);
}

export function aheadAbout(detail: SiteDetail): HowWeKnow {
  const a = detail.ahead;
  const chance = new Map([...a.projects, ...a.new_rules].map((p) => [p.id, p.chance]));
  return {
    title: `${mw(a.realistic_mw)} MW realistically ahead`,
    say: (
      <>
        We took each project still waiting at {detail.site} and multiplied its size by its chance of still being
        built, given how long it has already waited. Those chances come from similar projects across California.
        Projects from 2023&apos;s new-rules batch are listed but not added in, because nothing like them has finished
        yet.
      </>
    ),
    tally: [
      [a.projects.length, "waiting, counted"],
      [mw(a.waiting_mw), "MW they add up to"],
      [a.new_rules.length, "newer, not counted"],
    ],
    kind: "worked out",
    asOf: detail.as_of,
    rows: rowsOf(detail, [...a.projects, ...a.new_rules].map((p) => p.id)),
    extra: [
      { head: "Chance", cell: (r) => (chance.get(r.id) == null ? "unknown" : pct(chance.get(r.id) as number)) },
      {
        head: "Counts as",
        cell: (r) => {
          const c = chance.get(r.id);
          return c == null || r.mw == null ? "not added" : `${Math.round(r.mw * c)} MW`;
        },
      },
    ],
  };
}

/** One waiting project: its size, how long it has waited, and what it counts as. */
export function projectAbout(detail: SiteDetail, p: SiteDetail["ahead"]["projects"][number]): HowWeKnow {
  return {
    title: p.chance == null ? `${p.id}: odds unknown` : `${p.id} counts as ${mw(p.mw * p.chance)} MW`,
    say:
      p.chance == null ? (
        <>It applied under the 2023 rules, so it&apos;s shown at its full {mw(p.mw)} MW and never added in.</>
      ) : (
        <>
          It has waited {yrs(p.waited_years)} years. Of {p.compared_with ? plainGroup(p.compared_with) : "similar projects"}{" "}
          still waiting after that long, {pct(p.chance)} were later built, so its {mw(p.mw)} MW count as{" "}
          {mw(p.mw * p.chance)} MW.
        </>
      ),
    kind: "worked out",
    asOf: detail.as_of,
    rows: rowsOf(detail, [p.id]),
  };
}

export function newRulesAbout(detail: SiteDetail): HowWeKnow {
  const a = detail.ahead;
  return {
    title: `${mw(a.new_rules_mw)} MW from new-rules projects`,
    say: (
      <>
        Projects that applied under the 2023 rules are shown at their full size and never added to the realistic
        figure: none has finished under those rules yet, so there&apos;s no history to judge their odds.
      </>
    ),
    kind: "worked out",
    asOf: detail.as_of,
    rows: rowsOf(
      detail,
      a.new_rules.map((p) => p.id),
    ),
  };
}
