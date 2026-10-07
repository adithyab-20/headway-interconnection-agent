"use client";

// "The odds": three plain answers first, then four tabs of detail.

import type { HowWeKnow } from "@/components/Drawer";
import { Dots, OutcomeKey } from "@/components/Dots";
import { known, PROJECT_TYPES, type Odds, type ProjectType, type SiteDetail, type SiteSummary } from "@/shared/api";
import { in100, mw, pct } from "@/shared/format";
import { Arrow, Chat, Info } from "@/shared/icons";
import { Curve, CrowdBar, WaitScale } from "./charts";
import { aheadAbout, chanceAbout, newRulesAbout, projectAbout, waitAbout } from "./howWeKnow";
import { plainGroup, rungLabel, stepWords, typeName } from "./words";

export type Project = { type: ProjectType | null; mw: number; place: string };
export type Tab = "fared" | "ahead" | "grid" | "compared";
const YEARS = [3, 5, 7, 10];

export function Overview(props: {
  detail: SiteDetail;
  odds: Odds | null;
  oddsError: string | null;
  sites: SiteSummary[] | null;
  project: Project;
  setProject: (p: Project) => void;
  years: number;
  setYears: (n: number) => void;
  group: string | null;
  setGroup: (g: string | null) => void;
  tab: Tab;
  setTab: (t: Tab) => void;
  why: (about: HowWeKnow) => void;
  askAbout: (question: string) => void;
}) {
  const { detail, odds, project, years, why, tab } = props;
  const a = detail.ahead;
  const o = odds?.by_years[String(years)];
  const counted = props.sites?.filter((s) => s.waiting_projects > 0) ?? [];
  const share = counted.length
    ? Math.round((counted.filter((s) => s.realistic_mw < a.realistic_mw).length / counted.length) * 100)
    : null;
  const used = odds?.ladder.find((r) => r.used);
  const siteRung = odds?.ladder.find((r) => r.area_kind === "site");
  const onlyNew = a.waiting_projects === 0 && a.new_rules_projects > 0;
  const curveAt = odds?.curve.reduce(
    (b, d) => (Math.abs(d.years - years) < Math.abs(b.years - years) ? d : b),
    odds.curve[0],
  );

  return (
    <div style={{ display: "grid", gap: 20 }}>
      <div className="madlib">
        For a{" "}
        <select
          aria-label="Project type"
          value={project.type ?? ""}
          onChange={(e) => props.setProject({ ...project, type: (e.target.value || null) as ProjectType | null })}
        >
          {PROJECT_TYPES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
          <option value="">any type of</option>
        </select>{" "}
        project of{" "}
        <input
          type="number"
          min={1}
          aria-label="Size in MW"
          defaultValue={project.mw}
          onBlur={(e) => {
            const v = Number(e.target.value);
            if (v > 0 && v !== project.mw) props.setProject({ ...project, mw: v });
          }}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        />{" "}
        MW, connecting at{" "}
        <select
          aria-label="Voltage"
          value={project.place}
          onChange={(e) => props.setProject({ ...project, place: e.target.value })}
        >
          {detail.places.map((p) => (
            <option key={p.place} value={p.place}>
              {p.voltage_kv ? `${p.voltage_kv} kV` : p.place}
            </option>
          ))}
        </select>
        :
      </div>

      {props.oddsError && <p className="notice">{props.oddsError}</p>}

      <div className="answers">
        <article className="answer" aria-label="Will it get built?">
          <span className="q">Will it get built?</span>
          {!odds ? (
            <p className="says muted">Working it out…</p>
          ) : !known(o) ? (
            <p className="says">
              We can&apos;t say for {years} years: {o ? o.refused : "no similar project has been watched that long."}
            </p>
          ) : (
            <>
              <div className="big t">
                <button
                  className="num-big"
                  onClick={() => {
                    const about = chanceAbout(odds, years, detail.as_of);
                    if (about) why(about);
                  }}
                >
                  {in100(o.chance)}
                  <small> in 100</small>
                </button>
              </div>
              <p className="says">similar projects were built within {years} years of applying.</p>
              <Dots
                built={in100(o.chance)}
                withdrew={Math.round((curveAt?.withdrawn ?? 0) * 100)}
                label={`Of 100 similar projects after ${years} years: ${in100(o.chance)} built`}
              />
              <OutcomeKey />
              <span className="range">
                Likely somewhere between {in100(o.range[0])} and {in100(o.range[1])} in 100.
              </span>
            </>
          )}
          <div className="years" role="group" aria-label="Within how many years">
            {YEARS.map((k) => (
              <button key={k} aria-pressed={k === years} onClick={() => props.setYears(k)}>
                {k} yrs
              </button>
            ))}
          </div>
          <div className="followups">
            <button onClick={() => props.askAbout(`How many projects have withdrawn at ${detail.site}?`)}>
              <Chat /> Ask: How many projects have withdrawn at {detail.site}?
            </button>
          </div>
          <div className="foot">
            <span>{known(o) ? `${o.projects} past projects` : ""}</span>
            {odds && known(o) && (
              <button className="link" onClick={() => why(chanceAbout(odds, years, detail.as_of) as HowWeKnow)}>
                How we know <Arrow />
              </button>
            )}
          </div>
        </article>

        <article className="answer" aria-label="How long does it take?">
          <span className="q">How long does it take?</span>
          {!odds ? (
            <p className="says muted">Working it out…</p>
          ) : !known(o) || o.typical_wait == null ? (
            <p className="says">None of the similar projects has been built yet, so there&apos;s no typical wait.</p>
          ) : (
            <>
              <div className="big t">
                <button
                  className="num-big"
                  onClick={() => why(waitAbout(odds, years, detail.as_of) as HowWeKnow)}
                >
                  {Math.round(o.typical_wait)}
                  <small> years</small>
                </button>
              </div>
              <p className="says">is typical, from applying to running, for the projects that did get built.</p>
              <WaitScale wait={o.typical_wait} range={o.wait_range} />
              {o.wait_range && (
                <span className="range">
                  Likely between {Math.round(o.wait_range[0])} and {Math.round(o.wait_range[1])} years.
                </span>
              )}
            </>
          )}
          <div className="followups">
            <button onClick={() => props.askAbout("Which waiting projects have been in line longest?")}>
              <Chat /> Ask: Which waiting projects have been in line longest?
            </button>
          </div>
          <div className="foot">
            <span>{known(o) ? `${o.built} built projects` : ""}</span>
            {odds && known(o) && o.typical_wait != null && (
              <button className="link" onClick={() => why(waitAbout(odds, years, detail.as_of) as HowWeKnow)}>
                How we know <Arrow />
              </button>
            )}
          </div>
        </article>

        <article className="answer unknownish" aria-label="How crowded is it?">
          <span className="q">How crowded is it?</span>
          {onlyNew ? (
            <p className="says">
              Only projects that applied under the 2023 rules are waiting here. Nothing under those rules has finished
              yet, so nobody can say how many will be built.
            </p>
          ) : (
            <>
              <div className="big t">
                <button className="num-big" onClick={() => why(aheadAbout(detail))}>
                  {mw(a.realistic_mw)}
                  <small> MW</small>
                </button>
              </div>
              <p className="says">
                of projects are realistically ahead of a new one here.
                {share != null && ` That's more than at ${share}% of substations.`}
              </p>
              <CrowdBar realistic={a.realistic_mw} range={a.realistic_range} waiting={a.waiting_mw} />
              <span className="range">
                Likely between {mw(a.realistic_range[0])} and {mw(a.realistic_range[1])} MW, out of {mw(a.waiting_mw)}{" "}
                MW waiting.
              </span>
            </>
          )}
          {a.new_rules_mw > 0 && (
            <div className="note">
              <Info />
              <span>
                Another{" "}
                <button className="num" onClick={() => why(newRulesAbout(detail))}>
                  {mw(a.new_rules_mw)} MW
                </button>{" "}
                applied under 2023&apos;s new rules. It&apos;s too soon to know how much of it will be built, so it
                isn&apos;t counted above.
              </span>
            </div>
          )}
          {detail.left_out.length > 0 && (
            <div className="pill out" style={{ justifySelf: "start" }}>
              {detail.left_out.length} left out by you
            </div>
          )}
          <div className="followups">
            <button onClick={() => props.askAbout("Which waiting projects have been in line longest?")}>
              <Chat /> Ask: Which waiting projects have been in line longest?
            </button>
          </div>
          <div className="foot">
            <span>{a.projects.length + a.new_rules.length} waiting projects</span>
            <button className="link" onClick={() => why(aheadAbout(detail))}>
              How we know <Arrow />
            </button>
          </div>
        </article>
      </div>

      {odds && known(o) && (
        <div className="basis">
          <Info />
          <span>
            These answers come from{" "}
            <b>
              {o.projects} past {plainGroup(odds.used)}
            </b>{" "}
            that applied before the 2023 rule change.
            {used && used.area_kind !== "voltage section" && used.area_kind !== "site" && siteRung && !siteRung.enough
              ? ` ${detail.site} itself has too few past projects to go on.`
              : ""}{" "}
            <button className="link" onClick={() => props.setTab("compared")}>
              How we chose them
            </button>
          </span>
        </div>
      )}

      <section className="deeper" aria-label="More detail">
        <div className="tabs" role="tablist">
          {(
            [
              ["fared", "How similar projects fared"],
              ["ahead", `Projects ahead (${a.projects.length + a.new_rules.length})`],
              ["grid", "Upgrades and costs"],
              ["compared", "Who we compared with"],
            ] as [Tab, string][]
          ).map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} onClick={() => props.setTab(k)}>
              {label}
            </button>
          ))}
        </div>
        <div className="tabpanel" role="tabpanel" key={tab}>
          {tab === "fared" &&
            (odds ? (
              <>
                <h3>How similar projects fared over time</h3>
                <p className="lead">
                  Out of every 100 similar projects, how many had been built, had withdrawn, or were still waiting, year
                  by year after applying.
                </p>
                <Curve curve={odds.curve} years={years} />
              </>
            ) : (
              <p className="muted">Working it out…</p>
            ))}
          {tab === "ahead" && <AheadTab detail={detail} why={why} />}
          {tab === "grid" && <GridTab detail={detail} />}
          {tab === "compared" && odds && (
            <ComparedTab
              odds={odds}
              site={detail.site}
              years={years}
              setGroup={props.setGroup}
              why={why}
              asOf={detail.as_of}
            />
          )}
        </div>
      </section>
    </div>
  );
}

function AheadTab({ detail, why }: { detail: SiteDetail; why: (about: HowWeKnow) => void }) {
  const a = detail.ahead;
  const left = new Set(detail.left_out);
  const all = [...a.projects, ...a.new_rules];
  const max = Math.max(1, ...all.map((p) => p.mw));
  const w = 260;
  const sc = (v: number) => (v / max) * w;
  const row = (p: (typeof all)[number]) => {
    const isNew = p.chance == null;
    return (
      <div key={p.id} className="prow">
        <div className="who">
          <b>
            {mw(p.mw)} MW {typeName(p)}
          </b>
          <span>
            <span className="mono">{p.id}</span> · applied {p.applied?.slice(0, 4) ?? "on an unknown date"},{" "}
            {stepWords(p.furthest_step)}
            {p.on_a_line ? " · on a line, counts at both ends" : ""}
          </span>
        </div>
        <svg className="viz" width="100%" height="16" viewBox={`0 0 ${w} 16`} style={{ maxWidth: w }} aria-hidden="true">
          <rect
            x="0"
            y="3"
            width={sc(p.mw)}
            height="10"
            rx="5"
            fill={isNew ? "var(--lav-wash)" : "var(--soft)"}
            stroke={isNew ? "var(--lav)" : "var(--rule-2)"}
          />
          {!isNew && <rect x="0" y="3" width={sc(p.mw * (p.chance ?? 0))} height="10" rx="5" fill="var(--t3)" />}
        </svg>
        <div className="counts">
          {isNew ? (
            <>
              <b className="t" style={{ color: "var(--lav-ink)" }}>
                <button className="num" onClick={() => why(projectAbout(detail, p))}>
                  ?
                </button>
              </b>
              <span>odds unknown</span>
            </>
          ) : (
            <>
              <b className="t">
                <button className="num" onClick={() => why(projectAbout(detail, p))}>
                  {mw(p.mw * (p.chance ?? 0))} MW
                </button>
              </b>
              <span>{pct(p.chance ?? 0)} likely to be built</span>
            </>
          )}
        </div>
      </div>
    );
  };
  return (
    <>
      <h3>Projects already waiting</h3>
      <p className="lead">
        Each bar is a waiting project&apos;s size. The filled part is how much of it is likely to be built, given how
        long it has already waited. Add up the filled parts and you get the {mw(a.realistic_mw)} MW above.
      </p>
      <div className="plist">
        {a.projects
          .slice()
          .sort((x, y) => y.mw * (y.chance ?? 0) - x.mw * (x.chance ?? 0))
          .map(row)}
        <div className="prow sum">
          <div className="who">
            <b>Realistically ahead</b>
          </div>
          <span />
          <div className="counts">
            <b className="t">
              <button className="num" onClick={() => why(aheadAbout(detail))}>
                {mw(a.realistic_mw)} MW
              </button>
            </b>
          </div>
        </div>
      </div>
      {left.size > 0 && (
        <p className="boxnote">
          Left out by you, and from the history the chances come from: {[...left].sort().join(", ")}.
        </p>
      )}
      {a.new_rules.length > 0 && (
        <>
          <h3 style={{ marginTop: 22 }}>Newer projects, under 2023&apos;s rules</h3>
          <p className="lead">
            No project under these rules has finished yet, so there&apos;s no history to judge their odds. We show
            them, but we don&apos;t add them in.
          </p>
          <div className="plist">{a.new_rules.map(row)}</div>
        </>
      )}
      {a.not_counted.length > 0 && (
        <p className="boxnote">
          Not counted, because the operator&apos;s file lacks what&apos;s needed:{" "}
          {a.not_counted.map((x) => `${x.id} (${x.why})`).join("; ")}.
        </p>
      )}
    </>
  );
}

function GridTab({ detail }: { detail: SiteDetail }) {
  const full = detail.bottlenecks.filter((b) => b.room_left_mw != null && b.room_left_mw <= 0).length;
  const costed = detail.bottlenecks.filter((b) => b.cost_per_kw != null).map((b) => b.cost_per_kw as number);
  const money = (lo: number | null, hi: number | null) =>
    lo != null && hi != null ? `About $${lo}–${hi} million` : lo != null ? `About $${lo} million` : "Cost not published";
  return (
    <>
      <div className="twin">
        <section aria-labelledby="h-upgrades">
          <h3 id="h-upgrades">Planned grid upgrades</h3>
          <p className="lead">Approved by the grid operator, paid for by all electricity customers.</p>
          {detail.upgrades.length === 0 && <p className="muted">None listed at {detail.site}.</p>}
          {detail.upgrades.map((u) => (
            <div key={u.plan_id} className="item">
              <b className="yr t">{u.year ?? "–"}</b>
              <div>
                <div className="nm">{u.name}</div>
                <div className="s">
                  {money(u.cost_low_musd, u.cost_high_musd)}
                  {u.utility ? ` · ${u.utility}` : ""}
                </div>
              </div>
            </div>
          ))}
        </section>
        <section aria-labelledby="h-bottlenecks">
          <h3 id="h-bottlenecks">Bottlenecks nearby</h3>
          <p className="lead">
            {detail.bottlenecks.length === 0
              ? `None listed behind ${detail.site}.`
              : `${full} of the ${detail.bottlenecks.length} lines and transformers ${detail.site} sits behind have no room left`}
            {costed.length > 0 && (
              <>
                . Adding room costs about{" "}
                <b>
                  ${Math.round(Math.min(...costed))}–{Math.round(Math.max(...costed))} per kW
                </b>
              </>
            )}
            {detail.bottlenecks.length > 0 && "."}
          </p>
          {detail.bottlenecks.map((b) => (
            <div key={b.bottleneck} className="item" style={{ gridTemplateColumns: "minmax(0,1fr) auto" }}>
              <div>
                <div className="nm">{b.bottleneck}</div>
                <div className="s">
                  {b.room_left_mw == null
                    ? "Room not listed"
                    : b.room_left_mw <= 0
                      ? "Full"
                      : `${mw(b.room_left_mw)} MW of room left`}
                </div>
              </div>
              <div className="t" style={{ textAlign: "right", fontWeight: 650 }}>
                {b.cost_per_kw != null ? (
                  `$${Math.round(b.cost_per_kw)}/kW`
                ) : (
                  <span className="faint" style={{ fontWeight: 400 }}>
                    not costed
                  </span>
                )}
              </div>
            </div>
          ))}
        </section>
      </div>
      <p className="boxnote">
        Upgrades come from the grid operator&apos;s approved-projects tracker; costs to add room are its estimates, in
        2022 dollars. Neither box changes the odds above; they&apos;re here so you can see what&apos;s coming.
      </p>
    </>
  );
}

function ComparedTab({
  odds,
  site,
  years,
  setGroup,
  why,
  asOf,
}: {
  odds: Odds;
  site: string;
  years: number;
  setGroup: (g: string | null) => void;
  why: (about: HowWeKnow) => void;
  asOf: string;
}) {
  const w = 160;
  return (
    <>
      <h3>Who we compared with</h3>
      <p className="lead">
        We start with projects as close to yours as possible and widen the circle until there are enough to trust: at
        least 30 that finished one way or the other, and 10 that were built.
      </p>
      <ol className="steps" aria-label="Comparison groups, closest first">
        {odds.ladder.map((r) => {
          const est = r.chance && known(r.chance) ? r.chance : null;
          const prog = Math.min(1, r.resolved / 30);
          return (
            <li key={r.description} className={`step${r.enough ? " ok" : ""}${r.used ? " used" : ""}`}>
              <span className="dot" aria-hidden="true" />
              <div className="what">
                <b>{rungLabel(r, site)}</b>
                <span>
                  {r.description.split(", ").slice(0, -1).join(", ").replace("-", "–")} ·{" "}
                  <button
                    className="num"
                    onClick={() =>
                      why({
                        title: `${rungLabel(r, site)}: ${r.projects} past projects`,
                        say: (
                          <>
                            Every past {plainGroup(r.description)}: {r.resolved} finished (built or withdrew), and{" "}
                            {r.built} of those were built.
                          </>
                        ),
                        tally: [
                          [r.built, "built"],
                          [r.resolved - r.built, "withdrew"],
                          [r.projects - r.resolved, "still waiting"],
                        ],
                        kind: "worked out",
                        asOf,
                        rows: r.ids,
                      })
                    }
                  >
                    {r.resolved} finished, {r.built} built
                  </button>
                </span>
              </div>
              <svg className="viz" width="100%" height="10" viewBox={`0 0 ${w} 10`} style={{ maxWidth: w }} aria-hidden="true">
                <rect y="2" width={w} height="6" rx="3" fill="var(--soft)" />
                <rect y="2" width={prog * w} height="6" rx="3" fill={r.enough ? "var(--t2)" : "var(--rule-2)"} />
              </svg>
              <div className="fig">
                {r.used ? (
                  <>
                    {est ? `${in100(est.chance)} in 100` : "—"}
                    <span>in use</span>
                  </>
                ) : est ? (
                  <button className="btn sm" onClick={() => setGroup(r.description)}>
                    Use · {in100(est.chance)} in 100
                  </button>
                ) : (
                  <span style={{ fontWeight: 400, color: "var(--muted)" }}>{r.enough ? "no figure" : "too few"}</span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="boxnote">
        &quot;In 100&quot; is the chance of being built within {years} years. The bar shows how close each group comes to
        having enough finished projects.
      </p>
    </>
  );
}
