"use client";

import { useRef, useState } from "react";
import type { Odds } from "@/shared/api";
import { in100, mw, yrs } from "@/shared/format";

export function WaitScale({ wait, range }: { wait: number; range: [number, number] | null }) {
  const w = 300;
  const max = Math.max(15, Math.ceil(range?.[1] ?? wait));
  const sc = (v: number) => (v / max) * w;
  return (
    <svg
      className="chart"
      viewBox={`0 0 ${w} 40`}
      role="img"
      aria-label={`Typical wait ${yrs(wait)} years${range ? `, likely ${yrs(range[0])} to ${yrs(range[1])}` : ""}`}
    >
      <rect x="0" y="12" width={w} height="8" rx="4" fill="var(--soft)" />
      {range && <rect x={sc(range[0])} y="12" width={sc(range[1]) - sc(range[0])} height="8" rx="4" fill="var(--band)" />}
      <circle cx={sc(wait)} cy="16" r="7" fill="var(--t3)" stroke="var(--panel)" strokeWidth="2.5" />
      {[0, 5, 10, max].map((t) => (
        <text key={t} x={sc(t)} y="38" textAnchor={t === 0 ? "start" : t === max ? "end" : "middle"}>
          {t}
          {t === max ? " yrs" : ""}
        </text>
      ))}
    </svg>
  );
}

export function CrowdBar({ realistic, range, waiting }: { realistic: number; range: [number, number]; waiting: number }) {
  const w = 300;
  const sc = (v: number) => (waiting > 0 ? (v / waiting) * w : 0);
  return (
    <svg
      className="chart"
      viewBox={`0 0 ${w} 40`}
      role="img"
      aria-label={`${mw(realistic)} MW realistically ahead out of ${mw(waiting)} MW waiting`}
    >
      <rect x="0" y="12" width={w} height="8" rx="4" fill="var(--soft)" />
      <rect x="0" y="12" width={sc(realistic)} height="8" rx="4" fill="var(--t3)" />
      <rect x={sc(range[0])} y="10" width={Math.max(0, sc(range[1]) - sc(range[0]))} height="12" rx="6" fill="var(--band)" />
      <text x="0" y="38">
        0
      </text>
      <text x={w} y="38" textAnchor="end">
        {mw(waiting)} MW waiting
      </text>
    </svg>
  );
}

/** Out of every 100 similar projects: built, still waiting and withdrew, year by year. */
export function Curve({ curve, years }: { curve: Odds["curve"]; years: number }) {
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  if (curve.length < 2) return <p className="muted">Too little history to draw.</p>;
  const Wd = 760;
  const Hd = 280;
  const m = { l: 40, r: 118, t: 10, b: 34 };
  const maxY = curve[curve.length - 1].years;
  const x = (v: number) => m.l + (v / maxY) * (Wd - m.l - m.r);
  const y = (v: number) => m.t + (1 - v) * (Hd - m.t - m.b);
  type D = Odds["curve"][number];
  const area = (top: (d: D) => number, bot: (d: D) => number) =>
    curve.map((d, i) => `${i ? "L" : "M"}${x(d.years)},${y(top(d))}`).join("") +
    curve
      .slice()
      .reverse()
      .map((d) => `L${x(d.years)},${y(bot(d))}`)
      .join("") +
    "Z";
  const wTop = (d: D) => 1 - d.withdrawn;
  const last = curve[curve.length - 1];
  const nearest = (v: number) => curve.reduce((b, d) => (Math.abs(d.years - v) < Math.abs(b.years - v) ? d : b), curve[0]);
  const at = nearest(years);
  const ticks: number[] = [];
  for (let t = 0; t <= maxY; t += 2) ticks.push(t);
  const h = hover ? curve[hover.i] : null;
  return (
    <div style={{ position: "relative" }}>
      <svg
        ref={svg}
        className="chart"
        viewBox={`0 0 ${Wd} ${Hd}`}
        role="img"
        aria-label="Share of similar projects built, still waiting and withdrawn, by years since applying"
        onPointerMove={(e) => {
          const r = svg.current?.getBoundingClientRect();
          if (!r) return;
          const vx = (e.clientX - r.left) * (Wd / r.width);
          const yv = Math.max(0, Math.min(maxY, ((vx - m.l) / (Wd - m.l - m.r)) * maxY));
          const d = nearest(yv);
          setHover({ i: curve.indexOf(d), x: e.clientX, y: e.clientY });
        }}
        onPointerLeave={() => setHover(null)}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line className="grid" x1={m.l} x2={Wd - m.r} y1={y(t)} y2={y(t)} />
            <text x={m.l - 8} y={y(t) + 4} textAnchor="end">
              {t * 100}
            </text>
          </g>
        ))}
        <path d={area(() => 1, wTop)} fill="var(--sand)" />
        <path d={area(wTop, (d) => d.built)} fill="var(--sky)" />
        <path d={area((d) => d.built, () => 0)} fill="var(--t3)" />
        <path d={area((d) => d.built_range[1], (d) => d.built_range[0])} fill="var(--band)" />
        {ticks.map((t) => (
          <text key={t} x={x(t)} y={Hd - m.b + 18} textAnchor="middle">
            {t}
          </text>
        ))}
        <text x={(m.l + Wd - m.r) / 2} y={Hd - 2} textAnchor="middle">
          years after applying
        </text>
        {years <= maxY && (
          <>
            <line x1={x(years)} x2={x(years)} y1={m.t} y2={y(0)} stroke="var(--ink)" strokeWidth="1.2" />
            <text className="strong" x={x(years) + 6} y={m.t + 14}>
              year {years}: {in100(at.built)} built
            </text>
          </>
        )}
        <text className="strong" x={Wd - m.r + 10} y={y((1 + wTop(last)) / 2) + 4}>
          Withdrew · {in100(last.withdrawn)}
        </text>
        <text className="strong" x={Wd - m.r + 10} y={y((wTop(last) + last.built) / 2) + 4}>
          Waiting · {in100(last.still_waiting)}
        </text>
        <text className="strong" x={Wd - m.r + 10} y={y(last.built / 2) + 4}>
          Built · {in100(last.built)}
        </text>
        {h && <line x1={x(h.years)} x2={x(h.years)} y1={m.t} y2={y(0)} stroke="var(--ink-2)" />}
      </svg>
      {h && hover && (
        <div className="tip" style={{ left: hover.x + 14, top: hover.y + 14 }}>
          <span className="dim">{yrs(h.years)} years after applying, of 100</span>
          <br />
          <b>{in100(h.built)}</b> built{" "}
          <span className="dim">
            (likely {in100(h.built_range[0])}–{in100(h.built_range[1])})
          </span>
          <br />
          <b>{in100(h.still_waiting)}</b> still waiting
          <br />
          <b>{in100(h.withdrawn)}</b> withdrew
        </div>
      )}
      <div className="key" style={{ marginTop: 8 }}>
        <span>
          <i style={{ background: "var(--t3)" }} />
          built
        </span>
        <span>
          <i style={{ background: "var(--band)", boxShadow: "inset 0 0 0 1px var(--t3)" }} />
          likely range of built
        </span>
        <span>
          <i style={{ background: "var(--sky)" }} />
          still waiting
        </span>
        <span>
          <i style={{ background: "var(--sand)" }} />
          withdrew
        </span>
        <span>· per 100 projects</span>
      </div>
    </div>
  );
}
