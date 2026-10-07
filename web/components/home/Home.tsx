"use client";

// The landing page: what the queue is and what usually happens in it, before any substation.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Dots, OutcomeKey } from "@/components/Dots";
import { Term } from "@/components/Term";
import { api, type Overview, type SiteSummary, type YearCounts } from "@/shared/api";
import { NAME } from "@/shared/brand";
import { classOf, classVar, dateLong, in100, mw } from "@/shared/format";
import { Arrow, Back, Search } from "@/shared/icons";

const TYPES: [string, string][] = [
  ["Solar", "Solar only"],
  ["Solar + battery", "Solar + battery"],
  ["Battery", "Battery only"],
  ["Wind", "Wind"],
  ["Gas", "Gas"],
];
const SIZES: [string, string][] = [
  ["Under 50 MW", "under 50 MW"],
  ["50–150 MW", "50-150 MW"],
  ["150–300 MW", "150-300 MW"],
  ["Over 300 MW", "300 MW and over"],
];

export function Home() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    api
      .overview()
      .then(setOverview)
      .catch((e: Error) => setFailed(e.message));
    api
      .sites()
      .then((s) => setSites(s.sites))
      .catch((e: Error) => setFailed(e.message));
  }, []);
  const total = useMemo(
    () =>
      overview
        ? Object.values(overview.years).reduce((n, y) => n + (y.built ?? 0) + (y.withdrawn ?? 0) + (y.waiting ?? 0), 0)
        : null,
    [overview],
  );

  return (
    <div className="home">
      <section className="hero">
        <div>
          <div className="eyebrow">A look at California&apos;s grid connection queue</div>
          <h1>What happens to power projects waiting to join California&apos;s grid</h1>
          <p className="lede">
            Before a new solar farm, wind farm or battery can send power to the grid, it applies to connect and waits in
            a <Term term="queue">queue</Term> while the grid operator studies it. {NAME} looks at what happened to the{" "}
            {total != null ? total.toLocaleString("en-US") : "…"} projects that applied under the old rules, and uses
            that history to estimate, at each <Term term="substation">substation</Term>, how likely a new project is to
            be built and how long it tends to take.
          </p>
          <div className="cta">
            <Link className="btn p lg" href="/map">
              Explore the map <Arrow />
            </Link>
            <a className="btn lg" href="#history">
              How it works
            </a>
          </div>
        </div>
        <div className="try" aria-live="polite">
          {overview ? <TryType overview={overview} /> : <p className="muted">{failed ?? "Loading the history…"}</p>}
        </div>
      </section>

      <section className="chapter" id="history">
        <div className="head2">
          <div className="eyebrow">The history</div>
          <h2>Most projects leave the queue before they&apos;re built</h2>
          <p>
            Each dot below is one project that applied to connect to California&apos;s grid, placed by the year it
            applied. Step through to see what happened to them.
          </p>
        </div>
        <div className="story">{overview ? <Story years={overview.years} /> : <p className="muted">Loading…</p>}</div>
      </section>

      <section className="chapter">
        <div className="head2">
          <div className="eyebrow">Location</div>
          <h2>How crowded the queue is varies a lot by substation</h2>
          <p>
            Each bar below is a substation. Its height is the <Term term="mw">MW</Term> of projects realistically
            waiting there: each waiting project counted by its chance of being built, given how long it has already
            waited.
          </p>
        </div>
        <div className="strip">
          {sites ? <Strip sites={sites} /> : <p className="muted">Working out every substation. This takes a few seconds the first time.</p>}
        </div>
      </section>

      <section className="chapter">
        <div className="head2">
          <div className="eyebrow">Method</div>
          <h2>How the numbers are made</h2>
        </div>
        <div className="three">
          <div className="c">
            <span className="ic">
              <Search />
            </span>
            <h3>Traceable</h3>
            <p>Each number links to how it was worked out and the exact rows of the grid operator&apos;s data it came from.</p>
          </div>
          <div className="c">
            <span className="ic">
              <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                <path d="M4 9.5l3 3 7-7.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <h3>Checked by code</h3>
            <p>
              A language model drafts each written summary. Code then recalculates every number in it from the data, and
              anything that doesn&apos;t match is left out.
            </p>
          </div>
          <div className="c">
            <span className="ic">
              <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                <circle cx="9" cy="6.5" r="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
                <path d="M3.5 15.5c1-3 3-4.4 5.5-4.4s4.5 1.4 5.5 4.4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            </span>
            <h3>Reviewed by a person</h3>
            <p>
              Interpretations are labelled as opinions and wait for a reviewer to accept, reject or reword them. Leaving a
              project out recalculates everything that depends on it.
            </p>
          </div>
        </div>
      </section>

      <section className="about" aria-labelledby="h-about">
        <h2 id="h-about">About this project</h2>
        <div className="about-grid">
          <div>
            <h3>What it is</h3>
            <p>
              An independent project exploring how a language model can write analysis whose every number is checked
              against public data. It isn&apos;t affiliated with the grid operator.
            </p>
          </div>
          <div>
            <h3>Data</h3>
            <p>
              CAISO&apos;s interconnection queue report{overview ? ` of ${dateLong(overview.as_of)}` : ""}. Substation
              positions from OpenStreetMap and public filings; county boundaries from the US Census Bureau.
            </p>
          </div>
          <div>
            <h3>Method</h3>
            <p>
              For each group of similar past projects, the share built by each year after applying. Projects still
              waiting count only for the years they&apos;ve been watched. Likely ranges come from resampling, and past
              predictions are checked against what happened.
            </p>
          </div>
          <div>
            <h3>Limits</h3>
            <p>
              The history covers projects that applied before the <Term term="rules">2023 rule change</Term>; newer
              projects can&apos;t be scored yet. It describes past outcomes, not the physics of the grid, and doesn&apos;t
              replace a power-flow study.
            </p>
          </div>
        </div>
        <Link className="link" href="/map" style={{ marginTop: 6 }}>
          Explore the map <Arrow />
        </Link>
      </section>
    </div>
  );
}

function TryType({ overview }: { overview: Overview }) {
  const [type, setType] = useState("Solar + battery");
  const [size, setSize] = useState("150-300 MW");
  const d = overview.types[type]?.[size];
  return (
    <>
      <h2>Try a project type</h2>
      <div className="opts">
        <label id="l-type">Type</label>
        <div className="seg" role="group" aria-labelledby="l-type">
          {TYPES.map(([label, key]) => (
            <button key={key} aria-pressed={key === type} onClick={() => setType(key)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="opts">
        <label id="l-size">Size</label>
        <div className="seg" role="group" aria-labelledby="l-size">
          {SIZES.map(([label, key]) => (
            <button key={key} aria-pressed={key === size} onClick={() => setSize(key)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {!d || "refused" in d ? (
        <p className="fine">There&apos;s too little history for this kind of project to say.</p>
      ) : (
        <>
          <div className="result">
            <Dots
              className="dots"
              built={in100(d.chance)}
              withdrew={Math.round(d.withdrawn * 100)}
              label={`Of 100 similar projects after 10 years: ${in100(d.chance)} built, ${Math.round(d.withdrawn * 100)} withdrew`}
            />
            <div>
              <div className="big t">
                {in100(d.chance)}
                <small> in 100</small>
              </div>
              <p>
                similar projects across California were built within 10 years. {Math.round(d.withdrawn * 100)} withdrew;{" "}
                {Math.max(0, 100 - in100(d.chance) - Math.round(d.withdrawn * 100))} are still waiting.
              </p>
              <p className="fine" style={{ marginTop: 6 }}>
                Likely between {in100(d.range[0])} and {in100(d.range[1])} in 100 · from {d.projects} past projects
                {d.typical_wait ? ` · those built took about ${Math.round(d.typical_wait)} years` : ""}
              </p>
            </div>
          </div>
          <OutcomeKey />
        </>
      )}
      <p className="fine">
        This is the statewide history; it varies a lot by substation.{" "}
        <Link className="link" href="/map">
          Explore the map <Arrow />
        </Link>
      </p>
    </>
  );
}

// "newGone": new-rules projects that already withdrew (or, one day, were built).
type Kind = "built" | "waiting" | "new" | "withdrawn" | "newGone";

function Story({ years: byYear }: { years: Record<string, YearCounts> }) {
  const [step, setStep] = useState(0);
  const [tip, setTip] = useState<{ y: number; x: number; top: number } | null>(null);
  const years = Object.keys(byYear)
    .map(Number)
    .sort((a, b) => a - b);
  const count = (y: number, k: Kind) => {
    const c = byYear[String(y)] ?? {};
    if (k === "new") return c.new_rules_waiting ?? 0;
    if (k === "newGone") return (c.new_rules_withdrawn ?? 0) + (c.new_rules_built ?? 0);
    return c[k] ?? 0;
  };
  const tot = (k: Kind) => years.reduce((s, y) => s + count(y, k), 0);
  const built = tot("built");
  const withdrew = tot("withdrawn");
  const waiting = tot("waiting");
  const newW = tot("new");
  const newAll = newW + tot("newGone");
  const newYears = years.filter((y) => count(y, "new") + count(y, "newGone") > 0);
  const since = years.find((y) => count(y, "waiting") > 0);
  const steps: [string, string, Partial<Record<Kind, boolean>>][] = [
    [`${(built + withdrew + waiting).toLocaleString("en-US")} projects asked to connect under the old rules.`, "Each dot is one of them, stacked by the year it applied.", {}],
    [`${built} were built.`, `That's about ${Math.round((built / (built + withdrew)) * 100)} in every 100 that reached an outcome.`, { built: true }],
    [`${withdrew.toLocaleString("en-US")} withdrew.`, "Withdrawing is by far the most common outcome.", { built: true, withdrawn: true }],
    [`${waiting} are still waiting.`, `Some have been in line since ${since}.`, { built: true, withdrawn: true, waiting: true }],
    [
      `And in ${newYears.join(" and ") || "2025"}, ${newAll} more applied under the new rules.`,
      `${newW} of them are still waiting. Nothing under these rules has finished yet, so their odds can't be known.`,
      { built: true, withdrawn: true, waiting: true, new: true, newGone: true },
    ],
  ];
  const [title, sub, on] = steps[step];
  const perRow = 6;
  const d = 5.2;
  const gap = 1.4;
  const colW = perRow * (d + gap);
  const colGap = 9;
  const top = 8;
  const order: Kind[] = ["built", "waiting", "new", "withdrawn", "newGone"];
  const columnTotal = (y: number) => order.reduce((s, k) => s + count(y, k), 0);
  const maxN = Math.max(...years.map(columnTotal));
  const plotH = Math.ceil(maxN / perRow) * (d + gap);
  const Wd = years.length * (colW + colGap);
  const Hd = top + plotH + 26;
  const fill: Record<Kind, string> = {
    built: "var(--t3)",
    withdrawn: "var(--sand-dot)",
    newGone: "var(--sand-dot)",
    waiting: "var(--panel)",
    new: "var(--lav)",
  };
  const keyItems = (
    [
      ["built", "var(--t3)", "built"],
      ["waiting", "", "still waiting"],
      ["new", "var(--lav)", "new rules, still waiting"],
      ["withdrawn", "var(--sand-dot)", "withdrew"],
    ] as [Kind, string, string][]
  ).filter(([k]) => on[k]);
  return (
    <>
      <div className="caption">
        <p>
          {title}
          <span>{sub}</span>
        </p>
        <div className="stepper">
          <button className="btn sm" aria-label="Previous" disabled={step === 0} onClick={() => setStep(step - 1)}>
            <Back />
          </button>
          <div className="pips">
            {steps.map((_, i) => (
              <button key={i} aria-label={`Step ${i + 1}`} aria-current={i === step} onClick={() => setStep(i)} />
            ))}
          </div>
          <button className="btn p sm" onClick={() => setStep(step === steps.length - 1 ? 0 : step + 1)}>
            {step === steps.length - 1 ? (
              "Start again"
            ) : (
              <>
                Next <Arrow />
              </>
            )}
          </button>
        </div>
      </div>
      <svg
        className="dotfield"
        viewBox={`0 0 ${Wd} ${Hd}`}
        role="img"
        aria-label="One dot per project, by year applied, coloured by what happened to it"
        onPointerLeave={() => setTip(null)}
      >
        {years.map((y, ci) => {
          const x0 = ci * (colW + colGap);
          const dots: React.ReactNode[] = [];
          let i = 0;
          for (const k of order)
            for (let j = 0; j < count(y, k); j++, i++) {
              const lit = on[k];
              dots.push(
                <circle
                  key={`${k}${j}`}
                  cx={(x0 + (i % perRow) * (d + gap) + d / 2).toFixed(1)}
                  cy={(top + plotH - Math.floor(i / perRow) * (d + gap) - d / 2).toFixed(1)}
                  r={d / 2}
                  fill={lit ? fill[k] : "var(--unlit)"}
                  stroke={lit && k === "waiting" ? "var(--sky-edge)" : "none"}
                  strokeWidth={lit && k === "waiting" ? 1.1 : 0}
                />,
              );
            }
          return (
            <g key={y}>
              {dots}
              {(y % 5 === 0 || y === years[0] || y === years[years.length - 1]) && (
                <text x={x0 + colW / 2} y={Hd - 6} textAnchor="middle">
                  {y}
                </text>
              )}
              <rect
                x={x0 - colGap / 2}
                y={0}
                width={colW + colGap}
                height={Hd}
                fill="transparent"
                onPointerMove={(e) => setTip({ y, x: e.clientX, top: e.clientY })}
              />
            </g>
          );
        })}
      </svg>
      {tip && (
        <div className="tip" style={{ left: tip.x + 14, top: tip.top + 14 }}>
          <b>{tip.y}</b> · {columnTotal(tip.y)} applied
          <br />
          {count(tip.y, "built")} built · {count(tip.y, "withdrawn") + count(tip.y, "newGone")} withdrew ·{" "}
          {count(tip.y, "waiting") + count(tip.y, "new")} still waiting
        </div>
      )}
      <div className="key">
        {keyItems.length ? (
          keyItems.map(([k, c, l]) => (
            <span key={k}>
              <i style={k === "waiting" ? { boxShadow: "inset 0 0 0 1.5px var(--sky-edge)" } : { background: c }} />
              {l}
            </span>
          ))
        ) : (
          <span>
            <i style={{ background: "var(--rule-2)" }} />a project
          </span>
        )}
      </div>
    </>
  );
}

function Strip({ sites: all }: { sites: SiteSummary[] }) {
  const router = useRouter();
  const [hover, setHover] = useState<{ s: SiteSummary; x: number; y: number } | null>(null);
  const sites = all.filter((s) => s.waiting_projects > 0).sort((a, b) => b.realistic_mw - a.realistic_mw);
  const Wd = 1000;
  const Hd = 230;
  const m = { l: 44, r: 8, t: 16, b: 28 };
  const max = Math.max(4000, Math.ceil(sites[0].realistic_mw / 1000) * 1000);
  const bw = (Wd - m.l - m.r) / sites.length;
  const y = (v: number) => m.t + (1 - v / max) * (Hd - m.t - m.b);
  const sorted = sites.map((s) => s.realistic_mw).sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const first = sites[0];
  const quiet = sites.filter((s) => s.realistic_mw <= 300).length;
  const ticks = [];
  for (let t = 0; t <= max; t += 1000) ticks.push(t);
  return (
    <>
      <svg viewBox={`0 0 ${Wd} ${Hd}`} role="img" aria-label={`${sites.length} substations ranked by MW realistically ahead`} onPointerLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={Wd - m.r} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
            <text x={m.l - 8} y={y(t) + 4} textAnchor="end">
              {t ? t.toLocaleString("en-US") : 0}
            </text>
          </g>
        ))}
        {sites.map((s, i) => (
          <rect
            key={s.site}
            x={(m.l + i * bw + 0.6).toFixed(1)}
            y={y(s.realistic_mw).toFixed(1)}
            width={Math.max(1, bw - 1.2).toFixed(1)}
            height={(y(0) - y(s.realistic_mw)).toFixed(1)}
            rx="1.5"
            fill={classVar(classOf(s.realistic_mw))}
            opacity={hover?.s === s ? 0.6 : 1}
          />
        ))}
        <text className="lab" x={m.l + bw + 6} y={y(first.realistic_mw) + 4}>
          {first.site}: {mw(first.realistic_mw)} MW
        </text>
        <line x1={m.l} x2={Wd - m.r} y1={y(median)} y2={y(median)} stroke="var(--ink-2)" strokeWidth="1" />
        <text className="lab" x={Wd - m.r} y={y(median) - 8} textAnchor="end">
          Half have under {mw(median)} MW
        </text>
        <text x={m.l} y={Hd - 6}>
          Busiest
        </text>
        <text x={Wd - m.r} y={Hd - 6} textAnchor="end">
          Calmest · {sites.length} substations
        </text>
        {sites.map((s, i) => (
          <rect
            key={`hit-${s.site}`}
            x={(m.l + i * bw).toFixed(1)}
            y={m.t}
            width={bw.toFixed(1)}
            height={Hd - m.t - m.b}
            fill="transparent"
            style={{ cursor: "pointer" }}
            onPointerMove={(e) => setHover({ s, x: e.clientX, y: e.clientY })}
            onClick={() => router.push(`/substations/${encodeURIComponent(s.site)}`)}
          />
        ))}
      </svg>
      {hover && (
        <div className="tip" style={{ left: hover.x + 14, top: hover.y + 14 }}>
          <b>{hover.s.site}</b>
          {hover.s.county ? ` · ${hover.s.county} County` : ""}
          <br />
          {mw(hover.s.realistic_mw)} MW realistically ahead
        </div>
      )}
      <p className="muted small" style={{ margin: "10px 0 0" }}>
        {quiet} of {sites.length} substations have under 300 MW realistically ahead. Hover a bar to see which one; click
        it to open its page.
      </p>
    </>
  );
}
