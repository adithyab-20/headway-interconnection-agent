"use client";

// "How we know": what a number means, how it was worked out, and the exact rows behind it.

import { useEffect, useRef, useState } from "react";
import { api, type Row } from "@/shared/api";
import { dateLong } from "@/shared/format";
import { Arrow, Check, Close, Info } from "@/shared/icons";

export type HowWeKnow = {
  title: string;
  say?: React.ReactNode;
  tally?: [React.ReactNode, string][];
  // "checked": the number passed the checker (a write-up). "worked out": the page's own
  // figure, worked out by the tested functions from these rows.
  kind: "checked" | "worked out";
  asOf: string;
  rows: Row[] | string[]; // rows, or the ids to fetch them by
  // Extra columns for this kind of row (realistic MW ahead: the chance and what it counts as).
  extra?: { head: string; cell: (r: Row) => React.ReactNode }[];
};

const WHAT_HAPPENED = { built: "Built", withdrawn: "Withdrew", waiting: "Still waiting" } as const;

export function Drawer({ about, onClose }: { about: HowWeKnow; onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null);
  const [rows, setRows] = useState<Row[] | null>(
    typeof about.rows[0] === "string" ? null : (about.rows as Row[]),
  );
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      before?.focus?.();
    };
  }, [onClose]);

  useEffect(() => {
    if (rows !== null || about.rows.length === 0) return;
    api
      .rows(about.rows as string[])
      .then((r) => setRows(r.rows))
      .catch((e: Error) => setFailed(e.message));
  }, [about.rows, rows]);

  const shown = rows ?? [];
  const count = rows === null ? about.rows.length : rows.length;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="dr-h">
        <header>
          <div>
            <div className="muted small">How we know</div>
            <h2 id="dr-h">{about.title}</h2>
          </div>
          <button ref={close} className="btn q sm" onClick={onClose} aria-label="Close">
            <Close />
          </button>
        </header>
        <div className="body">
          {about.say && <p style={{ margin: 0, color: "var(--ink-2)" }}>{about.say}</p>}
          {about.tally && (
            <div className="tally">
              {about.tally.map(([v, label]) => (
                <div key={label}>
                  <b className="t">{v}</b>
                  <span>{label}</span>
                </div>
              ))}
            </div>
          )}
          {about.kind === "checked" ? (
            <div className="verified">
              <Check />
              <div>
                <b>Checked</b>
                <span>
                  Code recalculated this number from the rows below, from CAISO&apos;s queue report of{" "}
                  {dateLong(about.asOf)}, using all of them. It matched.
                </span>
              </div>
            </div>
          ) : (
            <div className="verified" style={{ background: "var(--accent-wash)", color: "var(--accent)" }}>
              <Info />
              <div>
                <b>Worked out from the data</b>
                <span>
                  Tested code worked this out from the rows below, from CAISO&apos;s queue report of{" "}
                  {dateLong(about.asOf)}.
                </span>
              </div>
            </div>
          )}
          {failed ? (
            <p className="notice">The rows couldn&apos;t be loaded: {failed}</p>
          ) : (
            <details className="rows">
              <summary>
                See all {count.toLocaleString("en-US")} source row{count === 1 ? "" : "s"} <Arrow />
              </summary>
              <div className="scroll-x">
                <table className="t">
                  <thead>
                    <tr>
                      <th>Project</th>
                      <th>Applied</th>
                      <th className="r">MW</th>
                      <th>What happened</th>
                      <th className="r">Years</th>
                      {about.extra?.map((x) => (
                        <th key={x.head} className="r">
                          {x.head}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((r) => (
                      <tr key={r.id}>
                        <td className="mono">{r.id}</td>
                        <td className="t">{r.applied?.slice(0, 4) ?? "–"}</td>
                        <td className="r t">{r.mw != null ? Math.round(r.mw) : "–"}</td>
                        <td>
                          {WHAT_HAPPENED[r.status]}
                          {r.rules === "2023 batch" && <span className="pill lav"> 2023 rules</span>}
                          {r.date_estimated && (
                            <span className="pill" title="The operator's file has no date, so it was estimated">
                              {" "}
                              date estimated
                            </span>
                          )}
                        </td>
                        <td className="r t">{r.years != null ? r.years.toFixed(1) : "–"}</td>
                        {about.extra?.map((x) => (
                          <td key={x.head} className="r t">
                            {x.cell(r)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
      </aside>
    </>
  );
}
