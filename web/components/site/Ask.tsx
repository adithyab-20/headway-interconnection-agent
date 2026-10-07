"use client";

// Ask: a workspace for one substation and one project. On the left, what we're looking at,
// all of it pointable. On the right, the conversation. Free questions go to the assistant
// (checked by code before they're shown); the three guided actions work from the page's own
// figures and propose changes that apply only once confirmed.

import { useEffect, useRef, useState } from "react";
import type { HowWeKnow } from "@/components/Drawer";
import { api, ApiError, known, type Answer, type Assessment, type Odds, type SiteDetail } from "@/shared/api";
import { dateLong, in100, mw, yrs } from "@/shared/format";
import { AskMark, Check, Close, Chat, Doc, Info, Search, Swap } from "@/shared/icons";
import { aheadAbout, chanceAbout, newRulesAbout, waitAbout } from "./howWeKnow";
import { FactText } from "./Writeup";
import { plainGroup, rungLabel, typeName } from "./words";

export type NumKey = "chance" | "wait" | "ahead" | "new";

type Proposal = {
  description: React.ReactNode;
  change: { label: string; before: string; after: string } | null;
  leaveOut: string[];
  group: string | null;
  why: string;
  agentAnswerId: string | null;
  status: "open" | "applied" | "skipped" | "failed";
  note?: string;
};

export type Msg =
  | { who: "you"; text: string; refs?: string[] }
  | { who: "bot"; kind: "answer"; answer: Answer; added: boolean }
  | { who: "bot"; kind: "explain"; key: NumKey }
  | ({ who: "bot"; kind: "proposal" } & Proposal)
  | { who: "bot"; kind: "cant"; title: string; why: string; tabGrid?: boolean }
  | { who: "bot"; kind: "pick"; what: "number" | "group" | "projects"; done: boolean };

type Ref = { label: string; ids?: string[] };
export type Pending = { ask: string } | { group: string };

const LOOKUP_WORDS: Record<string, string> = {
  chance_of_being_built: "Worked out the chance of being built",
  realistic_mw_ahead: "Worked out the MW realistically ahead",
  list_projects: "Listed projects",
};

const SUGGESTED = (site: string) => [`How many projects have withdrawn at ${site}?`, "What would it cost to connect here?"];

export function Ask(props: {
  site: string;
  detail: SiteDetail;
  odds: Odds | null;
  years: number;
  projectLabel: string;
  assessment: Assessment | null;
  setAssessment: (a: Assessment) => void;
  ensureAssessment: () => Promise<Assessment | string>;
  msgs: Msg[];
  setMsgs: React.Dispatch<React.SetStateAction<Msg[]>>;
  changes: string[];
  // Apply a change to the page, and to the write-up unless it's already there. Returns a
  // problem in plain words, or null.
  change: (c: { leaveOut: string[]; group: string | null; why: string; inWriteup: boolean }) => Promise<string | null>;
  why: (about: HowWeKnow) => void;
  openTab: (tab: "grid") => void;
  openWriteup: () => void;
  // Something started from another view: a question, or a comparison group to propose.
  pending: Pending | null;
  clearPending: () => void;
}) {
  const { site, detail, odds, years, msgs, setMsgs, assessment } = props;
  const [busy, setBusy] = useState<{ steps: string[]; at: number } | null>(null);
  const [draft, setDraft] = useState("");
  const [refs, setRefs] = useState<Ref[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reason, setReason] = useState("");
  const [ctxOpen, setCtxOpen] = useState(false);
  const body = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const final = !!assessment?.final;
  const leftOut = new Set(detail.left_out);
  const waiting = [...detail.ahead.projects, ...detail.ahead.new_rules];
  const o = odds?.by_years[String(years)];

  useEffect(() => {
    if (msgs.length || busy) body.current?.scrollTo({ top: body.current.scrollHeight });
  }, [msgs, busy]);

  const say = (m: Msg) => setMsgs((all) => [...all, m]);
  const update = (i: number, m: Partial<Msg>) =>
    setMsgs((all) => all.map((x, j) => (j === i ? ({ ...x, ...m } as Msg) : x)));

  // Steps shown while waiting, one after another; the last stays until the reply comes.
  async function working<T>(steps: string[], run: () => Promise<T>): Promise<T> {
    setBusy({ steps, at: 0 });
    const timer = setInterval(
      () => setBusy((b) => (b && b.at < b.steps.length - 1 ? { ...b, at: b.at + 1 } : b)),
      900,
    );
    try {
      return await run();
    } finally {
      clearInterval(timer);
      setBusy(null);
    }
  }

  async function send(text: string, withRefs: Ref[] = refs) {
    if (busy || final || !text.trim()) return;
    const request = withRefs.length ? `About ${withRefs.map((r) => r.label).join("; ")}: ${text}` : text;
    say({ who: "you", text, refs: withRefs.map((r) => r.label) });
    setDraft("");
    setRefs([]);
    await working(
      assessment
        ? ["Reading your question", "Looking it up in the queue data", "Checking the numbers against the data"]
        : ["Writing the assessment first, so answers can join it", "Reading your question", "Checking the numbers against the data"],
      async () => {
        const made = await props.ensureAssessment();
        if (typeof made === "string") {
          say({ who: "bot", kind: "cant", title: "Questions need the assistant, which isn't available here", why: made });
          return;
        }
        try {
          const res = await api.ask(made.id, request);
          props.setAssessment(res.assessment);
          await answered(res.answer);
        } catch (e) {
          say({
            who: "bot",
            kind: "cant",
            title: e instanceof ApiError && e.status === 429 ? "No more questions for this write-up" : "That didn't work",
            why: (e as Error).message,
          });
        }
      },
    );
  }

  async function answered(answer: Answer) {
    if (answer.cant_answer) {
      say({
        who: "bot",
        kind: "cant",
        title: "That's outside what this data can answer",
        why: answer.cant_answer,
        tabGrid: /cost|pay|price|line|carry|upgrade/i.test(answer.request),
      });
    } else if (answer.proposal) {
      const p = answer.proposal;
      const change = p.leave_out.length ? await aheadChange([...detail.left_out, ...p.leave_out]) : null;
      say({
        who: "bot",
        kind: "proposal",
        description: p.description,
        change,
        leaveOut: p.leave_out,
        group: p.comparison_group,
        why: p.why,
        agentAnswerId: answer.id,
        status: "open",
      });
    } else if (answer.claims.length) {
      say({ who: "bot", kind: "answer", answer, added: false });
    } else {
      say({
        who: "bot",
        kind: "cant",
        title: "No checked answer to show",
        why: "The assistant's answer didn't pass the checks against the data, so nothing from it is shown.",
      });
    }
  }

  async function aheadChange(ids: string[]): Promise<Proposal["change"]> {
    try {
      const after = await api.site(site, ids);
      return {
        label: "Realistically ahead",
        before: `${mw(detail.ahead.realistic_mw)} MW`,
        after: `${mw(after.ahead.realistic_mw)} MW`,
      };
    } catch {
      return null;
    }
  }

  async function proposeLeaving(ids: string[], why: string) {
    const ps = waiting.filter((p) => ids.includes(p.id) && p.chance != null && !leftOut.has(p.id));
    if (!ps.length) return;
    const change = await working(["Finding the projects", "Working out what would change"], () =>
      aheadChange([...detail.left_out, ...ps.map((p) => p.id)]),
    );
    say({
      who: "bot",
      kind: "proposal",
      description: (
        <>
          <p style={{ margin: 0 }}>
            Leave out{" "}
            <b>
              {ps.length} project{ps.length === 1 ? "" : "s"}
            </b>{" "}
            still waiting at {site}:
          </p>
          <ul>
            {ps.map((p) => (
              <li key={p.id}>
                <span className="mono">{p.id}</span> · {mw(p.mw)} MW {typeName(p)}, applied {p.applied?.slice(0, 4)}
              </li>
            ))}
          </ul>
        </>
      ),
      change,
      leaveOut: ps.map((p) => p.id),
      group: null,
      why,
      agentAnswerId: null,
      status: "open",
    });
  }

  function proposeGroup(description: string) {
    const r = odds?.ladder.find((x) => x.description === description);
    if (!r || !known(r.chance) || !known(o)) return;
    say({
      who: "bot",
      kind: "proposal",
      description: (
        <p style={{ margin: 0 }}>
          Compare with{" "}
          <b>
            {r.projects} past {plainGroup(r.description)}
          </b>{" "}
          instead of the {o.projects} used now.{" "}
          <span className="small muted">
            {r.projects > o.projects
              ? "A bigger group gives a narrower range, but includes projects less like this one."
              : "A closer group is more like this project, but has fewer projects behind it."}
          </span>
        </p>
      ),
      change: {
        label: `Built within ${years} years`,
        before: `${in100(o.chance)} in 100`,
        after: `${in100(r.chance.chance)} in 100`,
      },
      leaveOut: [],
      group: r.description,
      why: `Compare with ${plainGroup(r.description)}`,
      agentAnswerId: null,
      status: "open",
    });
  }

  async function apply(i: number, p: Proposal) {
    let problem: string | null = null;
    let inWriteup = false;
    if (p.agentAnswerId && assessment) {
      try {
        props.setAssessment(await api.confirm(assessment.id, p.agentAnswerId));
        inWriteup = true;
      } catch (e) {
        problem = (e as Error).message;
      }
    }
    if (!problem) problem = await props.change({ leaveOut: p.leaveOut, group: p.group, why: p.why, inWriteup });
    update(i, problem ? { status: "failed", note: problem } : { status: "applied" });
  }

  function start(kind: "explain" | "leave" | "compare") {
    if (busy || final) return;
    if (kind === "leave" && selected.size) {
      const ids = [...selected];
      setSelected(new Set());
      say({ who: "you", text: `Leave ${ids.length === 1 ? "this" : "these"} out`, refs: ids });
      void proposeLeaving(ids, "");
      return;
    }
    say({
      who: "you",
      text: { explain: "Explain a number", leave: "Leave some projects out", compare: "Compare with a different group" }[kind],
    });
    say({ who: "bot", kind: "pick", what: ({ explain: "number", leave: "projects", compare: "group" } as const)[kind], done: false });
  }

  // A question or change started from another view ("Ask: ...", "Use" on the ladder).
  useEffect(() => {
    if (props.pending) {
      const p = props.pending;
      props.clearPending();
      if ("ask" in p) void send(p.ask, []);
      else {
        say({ who: "you", text: `Compare with ${plainGroup(p.group)}` });
        proposeGroup(p.group);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.pending]);

  const keyNumbers: { key: NumKey; label: string; short: string; value: React.ReactNode }[] = [
    ...(known(o)
      ? [
          {
            key: "chance" as const,
            label: `Chance of being built within ${years} years`,
            short: `${in100(o.chance)} in 100 built within ${years} years`,
            value: (
              <>
                {in100(o.chance)}
                <small>in 100</small>
              </>
            ),
          },
          ...(o.typical_wait != null
            ? [
                {
                  key: "wait" as const,
                  label: "Typical wait, if built",
                  short: `about ${Math.round(o.typical_wait)} years to be built`,
                  value: (
                    <>
                      {Math.round(o.typical_wait)}
                      <small>years</small>
                    </>
                  ),
                },
              ]
            : []),
        ]
      : []),
    {
      key: "ahead",
      label: "Realistically ahead",
      short: `${mw(detail.ahead.realistic_mw)} MW realistically ahead`,
      value: (
        <>
          {mw(detail.ahead.realistic_mw)}
          <small>MW</small>
        </>
      ),
    },
    ...(detail.ahead.new_rules_mw > 0
      ? [
          {
            key: "new" as const,
            label: "New-rules projects waiting",
            short: `${mw(detail.ahead.new_rules_mw)} MW of new-rules projects`,
            value: (
              <>
                {mw(detail.ahead.new_rules_mw)}
                <small>MW · odds unknown</small>
              </>
            ),
          },
        ]
      : []),
  ];
  const about = (key: NumKey): HowWeKnow | null =>
    key === "chance"
      ? odds && chanceAbout(odds, years, detail.as_of)
      : key === "wait"
        ? odds && waitAbout(odds, years, detail.as_of)
        : key === "ahead"
          ? aheadAbout(detail)
          : newRulesAbout(detail);
  const explain = (key: NumKey) => {
    const k = keyNumbers.find((x) => x.key === key);
    if (!k) return;
    say({ who: "you", text: `Explain the ${k.short}` });
    say({ who: "bot", kind: "explain", key });
  };
  const used = odds?.ladder.find((r) => r.used);
  const disabled = !!busy || final;

  return (
    <div className="ws">
      <aside className={`ctx-pane${ctxOpen ? "" : " closed"}`} aria-label="What we're looking at">
        <button className="ctx-toggle" aria-expanded={ctxOpen} onClick={() => setCtxOpen(!ctxOpen)}>
          What we&apos;re looking at <span>{ctxOpen ? "Hide" : "Show"}</span>
        </button>
        <p className="intro">Point at anything here to ask about it or change it.</p>
        <div className="ctx-sec">
          <h3>Project</h3>
          <div className="ctx-proj">{props.projectLabel}</div>
          <div className="muted small">Data of {dateLong(detail.as_of)}</div>
        </div>
        <div className="ctx-sec">
          <h3>Key numbers</h3>
          {keyNumbers.map((k) => (
            <div key={k.key} className="knum">
              <span className="k">{k.label}</span>
              <span className="v t">{k.value}</span>
              <span className="acts">
                <button className="mini" onClick={() => explain(k.key)} disabled={disabled}>
                  Explain
                </button>
                <button
                  className="mini"
                  disabled={disabled}
                  onClick={() => {
                    if (!refs.some((r) => r.label === k.short)) setRefs([...refs, { label: k.short }]);
                    box.current?.focus();
                  }}
                >
                  Ask about
                </button>
              </span>
            </div>
          ))}
        </div>
        <div className="ctx-sec">
          <h3>
            Compared with{" "}
            <button className="link" onClick={() => start("compare")} disabled={disabled}>
              Change
            </button>
          </h3>
          {known(o) && odds && (
            <div className="cgroup">
              <b>
                {o.projects} past {plainGroup(odds.used)}
              </b>
            </div>
          )}
          {used && used.area_kind === "California" && (
            <div className="muted small" style={{ marginTop: 4 }}>
              {site} itself has too few past projects to go on.
            </div>
          )}
        </div>
        <div className="ctx-sec">
          <h3>
            Projects waiting here <span className="t">{waiting.length}</span>
          </h3>
          <div className="plist2">
            {waiting
              .slice()
              .sort(
                (a, b) =>
                  Number(b.chance == null) - Number(a.chance == null) || b.mw * (b.chance ?? 0) - a.mw * (a.chance ?? 0),
              )
              .map((p) => {
                const on = selected.has(p.id);
                return (
                  <label key={p.id} className={`pick${on ? " on" : ""}`}>
                    <input
                      type="checkbox"
                      checked={on}
                      disabled={disabled}
                      onChange={(e) => {
                        const next = new Set(selected);
                        if (e.target.checked) next.add(p.id);
                        else next.delete(p.id);
                        setSelected(next);
                      }}
                    />
                    <span>
                      <b>
                        {mw(p.mw)} MW {typeName(p)}
                      </b>
                      <small>
                        <span className="mono">{p.id}</span> · applied {p.applied?.slice(0, 4)}
                      </small>
                    </span>
                    <span className="c">
                      {p.chance == null ? (
                        <small style={{ color: "var(--lav-ink)" }}>odds unknown</small>
                      ) : (
                        <>
                          {mw(p.mw * p.chance)}
                          <small> MW</small>
                        </>
                      )}
                    </span>
                  </label>
                );
              })}
            {detail.left_out.map((id) => (
              <div key={id} className="pick out">
                <span />
                <span>
                  <span className="mono">{id}</span>
                </span>
                <span className="c">
                  <small>left out</small>
                </span>
              </div>
            ))}
          </div>
          <p className="faint small" style={{ margin: "8px 0 0" }}>
            Right column: how many of its MW count as realistically ahead.
          </p>
        </div>
        {props.changes.length > 0 && (
          <div className="ctx-sec">
            <h3>Changes made</h3>
            {props.changes.map((c, i) => (
              <div key={i} className="small" style={{ display: "flex", gap: 6, marginBottom: 6 }}>
                <Check size={16} />
                <span>{c}</span>
              </div>
            ))}
          </div>
        )}
        {selected.size > 0 && (
          <div className="selbar">
            <b>{selected.size} selected</b>
            <button
              className="mini"
              onClick={() => {
                const ids = [...selected];
                setRefs([...refs, { label: ids.join(", "), ids }]);
                setSelected(new Set());
                box.current?.focus();
              }}
            >
              Ask about {selected.size === 1 ? "it" : "these"}
            </button>
            <button className="mini p" onClick={() => start("leave")}>
              Leave {selected.size === 1 ? "it" : "these"} out…
            </button>
            <button className="link" style={{ fontSize: 12.5 }} onClick={() => setSelected(new Set())}>
              Clear
            </button>
          </div>
        )}
      </aside>

      <section className="conv" aria-label="Conversation">
        <div className="conv-body" ref={body} aria-live="polite">
          {msgs.length === 0 ? (
            <Capabilities site={site} keyNumbers={keyNumbers} send={(q) => void send(q, [])} explain={explain} start={start} openWriteup={props.openWriteup} />
          ) : (
            msgs.map((m, i) => (
              <Message
                key={i}
                m={m}
                i={i}
                site={site}
                asOf={detail.as_of}
                final={final}
                assessment={assessment}
                setAssessment={props.setAssessment}
                update={update}
                why={props.why}
                apply={apply}
                send={(q) => void send(q, [])}
                keyNumbers={keyNumbers}
                explain={explain}
                about={about}
                odds={odds}
                years={years}
                proposeGroup={proposeGroup}
                proposeLeaving={(ids, why) => void proposeLeaving(ids, why)}
                waiting={detail.ahead.projects.filter((p) => !leftOut.has(p.id))}
                selected={selected}
                setSelected={setSelected}
                reason={reason}
                setReason={setReason}
                openTab={props.openTab}
                disabled={disabled}
              />
            ))
          )}
          {busy && (
            <div className="working" role="status">
              {busy.steps.slice(0, busy.at + 1).map((s, i) => (
                <span key={s}>
                  {i < busy.at ? <i className="ok" /> : <i className="spin" />}
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="composer">
          <div className="qa" role="group" aria-label="Guided actions">
            <button onClick={() => start("explain")} disabled={disabled}>
              <Search /> Explain a number
            </button>
            <button onClick={() => start("leave")} disabled={disabled}>
              Leave projects out
            </button>
            <button onClick={() => start("compare")} disabled={disabled}>
              Compare differently
            </button>
          </div>
          <div className="box">
            {refs.length > 0 && (
              <div className="chips-sm" style={{ gap: 4 }}>
                {refs.map((r, i) => (
                  <span key={r.label} className="ref">
                    {r.label}
                    <button aria-label={`Remove ${r.label}`} onClick={() => setRefs(refs.filter((_, j) => j !== i))}>
                      <Close size={12} />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="row3">
              <textarea
                ref={box}
                rows={1}
                value={draft}
                disabled={disabled}
                aria-label="Your question"
                placeholder={
                  refs.length
                    ? "What would you like to know or change about this?"
                    : `Ask about ${site}, or tell the assistant what to change`
                }
                onChange={(e) => {
                  setDraft(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(120, e.target.scrollHeight)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send(draft);
                  }
                }}
              />
              <button className="btn p sm" disabled={disabled || !draft.trim()} onClick={() => void send(draft)}>
                Ask
              </button>
            </div>
          </div>
          <div className="meta">
            <span>
              {final
                ? "The write-up is final, so no more changes can be made."
                : "Uses CAISO's queue data only. Numbers are checked before they're shown."}
            </span>
            {assessment && <span className="t">{assessment.questions_left} model calls left for this write-up</span>}
          </div>
        </div>
      </section>
    </div>
  );
}

function Capabilities({
  site,
  keyNumbers,
  send,
  explain,
  start,
  openWriteup,
}: {
  site: string;
  keyNumbers: { key: NumKey; short: string }[];
  send: (q: string) => void;
  explain: (k: NumKey) => void;
  start: (k: "explain" | "leave" | "compare") => void;
  openWriteup: () => void;
}) {
  const card = (icon: React.ReactNode, h: string, p: string, ex: React.ReactNode) => (
    <div className="cap">
      <div className="h">
        <span className="ic">{icon}</span>
        {h}
      </div>
      <p>{p}</p>
      <div className="ex">{ex}</div>
    </div>
  );
  return (
    <div className="caps">
      <h2>What the assistant can do here</h2>
      <p>
        It works only from the grid operator&apos;s queue data, for {site} and projects like this one. Every number it
        gives you is recalculated by code before you see it.
      </p>
      <div className="capgrid">
        {card(
          <Chat />,
          "Answer questions",
          `About past and waiting projects at ${site}, and the odds for projects like this one.`,
          SUGGESTED(site).slice(0, 1).map((q) => (
            <button key={q} onClick={() => send(q)}>
              &ldquo;{q}&rdquo;
            </button>
          )),
        )}
        {card(
          <Search />,
          "Explain a number",
          "How any number on the page was worked out, and the exact rows behind it.",
          keyNumbers.slice(0, 2).map((k) => (
            <button key={k.key} onClick={() => explain(k.key)}>
              Explain the {k.short}
            </button>
          )),
        )}
        {card(
          <Swap />,
          "Change what's counted",
          "Leave projects out, or compare with a different group. You see the effect first; nothing changes until you confirm.",
          <>
            <button onClick={() => start("leave")}>Leave some projects out</button>
            <button onClick={() => start("compare")}>Compare with a different group</button>
          </>,
        )}
        {card(
          <Doc />,
          "Build the write-up",
          "Keep the answers you want. They join the write-up as checked facts; any opinion waits for your review.",
          <button onClick={openWriteup}>Open the write-up</button>,
        )}
      </div>
      <div className="cant-list">
        <b>It can&apos;t</b> say what a project would pay to connect, describe what the power lines can carry, compare{" "}
        {site} with other substations, or forecast beyond what past projects show. If you ask, it will say so.
      </div>
    </div>
  );
}

function Message(props: {
  m: Msg;
  i: number;
  site: string;
  asOf: string;
  final: boolean;
  assessment: Assessment | null;
  setAssessment: (a: Assessment) => void;
  update: (i: number, m: Partial<Msg>) => void;
  why: (about: HowWeKnow) => void;
  apply: (i: number, p: Proposal) => Promise<void>;
  send: (q: string) => void;
  keyNumbers: { key: NumKey; label: string; short: string }[];
  explain: (k: NumKey) => void;
  about: (k: NumKey) => HowWeKnow | null;
  odds: Odds | null;
  years: number;
  proposeGroup: (description: string) => void;
  proposeLeaving: (ids: string[], why: string) => void;
  waiting: SiteDetail["ahead"]["projects"];
  selected: Set<string>;
  setSelected: (s: Set<string>) => void;
  reason: string;
  setReason: (s: string) => void;
  openTab: (tab: "grid") => void;
  disabled: boolean;
}) {
  const { m, i } = props;
  const who = <span className="who">Assistant</span>;
  if (m.who === "you") {
    return (
      <div className="msg you">
        {m.refs && m.refs.length > 0 && (
          <div className="refs">
            {m.refs.map((r) => (
              <span key={r} className="ref">
                {r}
              </span>
            ))}
          </div>
        )}
        <div className="bubble">{m.text}</div>
      </div>
    );
  }
  if (m.kind === "answer") {
    const facts = m.answer.claims.filter((c) => c.kind === "factual");
    const opinions = m.answer.claims.filter((c) => c.kind === "judgement");
    const rows = [...new Set(facts.flatMap((c) => c.parts.flatMap((p) => ("rows" in p ? p.rows : []))))];
    return (
      <div className="msg bot">
        {who}
        {facts.map((f) => (
          <div key={f.id} className="fact">
            <span>
              <Check />
            </span>
            <p>
              <FactText parts={f.parts} why={props.why} asOf={props.asOf} />
            </p>
          </div>
        ))}
        {opinions.map((j) => (
          <div key={j.id} className="opin">
            <span>
              <AskMark />
            </span>
            <p>
              {j.text}
              <small>Opinion · not checked by code</small>
            </p>
          </div>
        ))}
        <details className="trace">
          <summary>
            <Check size={16} /> {m.answer.lookups.length} lookup{m.answer.lookups.length === 1 ? "" : "s"} ·{" "}
            {facts.length} fact{facts.length === 1 ? "" : "s"} checked
            {m.answer.rejected ? ` · ${m.answer.rejected} left out because they didn't pass` : ""} · how this was
            answered
          </summary>
          <ol>
            {m.answer.lookups.map((l, k) => (
              <li key={k}>
                {LOOKUP_WORDS[l.tool] ?? l.tool}:{" "}
                <code>
                  {Object.entries(l.asked)
                    .map(([key, v]) => `${key.replace(/_/g, " ")} ${String(v)}`)
                    .join(", ")}
                </code>
                , {l.rows} row{l.rows === 1 ? "" : "s"}
              </li>
            ))}
            <li>Code recalculated every number from those rows, using all of them. All matched.</li>
          </ol>
        </details>
        <div className="acts">
          {m.added ? (
            <span className="done">
              <Check size={16} /> Added to the write-up{opinions.length ? "; the opinion is waiting for review" : ""}
            </span>
          ) : props.final ? null : (
            <button
              className="btn sm"
              onClick={async () => {
                if (!props.assessment) return;
                props.setAssessment(await api.add(props.assessment.id, m.answer.id));
                props.update(i, { added: true });
              }}
            >
              Add to write-up
            </button>
          )}
          {rows.length > 0 && (
            <button
              className="btn q sm"
              onClick={() =>
                props.why({
                  title: `${rows.length} row${rows.length === 1 ? "" : "s"} from the queue report`,
                  say: <>These are the exact projects the lookup returned. Code recalculated the answer from them.</>,
                  kind: "checked",
                  asOf: props.asOf,
                  rows,
                })
              }
            >
              See the rows
            </button>
          )}
        </div>
      </div>
    );
  }
  if (m.kind === "explain") {
    const about = props.about(m.key);
    return (
      <div className="msg bot">
        {who}
        {about ? (
          <>
            <p className="say">
              <b>{about.title}.</b> {about.say}
            </p>
            <div className="acts">
              <button className="btn q sm" onClick={() => props.why(about)}>
                See the rows
              </button>
            </div>
          </>
        ) : (
          <p className="say">There&apos;s no figure to explain for this one.</p>
        )}
      </div>
    );
  }
  if (m.kind === "proposal") {
    return (
      <div className="msg bot">
        {who}
        <div className={`prop${m.status !== "open" ? " closed" : ""}`}>
          <span className="lbl">
            {m.status === "open"
              ? "Proposed change · nothing applied yet"
              : m.status === "applied"
                ? "Change applied"
                : "Change not applied"}
          </span>
          {typeof m.description === "string" ? <p style={{ margin: 0 }}>{m.description}</p> : m.description}
          {m.change && (
            <div className="change">
              {m.change.label}: <s className="t">{m.change.before}</s> → <b className="t">{m.change.after}</b>
            </div>
          )}
          {m.why && <span className="small">Reason: &ldquo;{m.why}&rdquo;</span>}
          {m.leaveOut.length > 0 && (
            <span className="small muted">
              They&apos;d also be left out of the history the chances come from. Every fact that uses them is worked out
              and checked again; opinions resting on a number that moves come back for review.
            </span>
          )}
          {m.status === "open" ? (
            props.final ? (
              <span className="muted small">The write-up is final, so this can&apos;t be applied.</span>
            ) : (
              <div className="acts">
                <button className="btn p sm" onClick={() => void props.apply(i, m)}>
                  Make this change
                </button>
                <button className="btn q sm" onClick={() => props.update(i, { status: "skipped" })}>
                  Never mind
                </button>
              </div>
            )
          ) : m.status === "applied" ? (
            <span className="done">
              <Check size={16} /> Applied. Every number on the page was worked out again.
            </span>
          ) : (
            <span className="muted small">{m.note ?? "Nothing was changed."}</span>
          )}
        </div>
      </div>
    );
  }
  if (m.kind === "cant") {
    return (
      <div className="msg bot">
        {who}
        <div className="cant-reply">
          <div className="h">
            <Info /> {m.title}
          </div>
          <p>{m.why}</p>
          {m.tabGrid && (
            <p>
              This page does show planned upgrades near {props.site} and the operator&apos;s estimate of the cost to add
              room per kW.{" "}
              <button className="link" onClick={() => props.openTab("grid")}>
                Open Upgrades and costs
              </button>
            </p>
          )}
        </div>
      </div>
    );
  }
  // A guided action asking a short follow-up.
  const done = m.done || props.disabled;
  if (m.what === "number") {
    return (
      <div className="msg bot">
        {who}
        <p className="say">Which number should I explain?</p>
        <div className="choose">
          {props.keyNumbers.map((k) => (
            <button
              key={k.key}
              className="opt"
              disabled={done}
              onClick={() => {
                props.update(i, { done: true });
                props.explain(k.key);
              }}
            >
              {k.label}
              <span>{k.short}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }
  if (m.what === "group") {
    return (
      <div className="msg bot">
        {who}
        <p className="say">
          Which group should projects like this one be compared with? Narrower groups are closer to {props.site} but
          need enough finished projects to be trusted.
        </p>
        <div className="choose">
          {props.odds?.ladder.map((r) => {
            const est = r.chance && known(r.chance) ? r.chance : null;
            return (
              <button
                key={r.description}
                className="opt"
                disabled={done || !est || r.used}
                onClick={() => {
                  props.update(i, { done: true });
                  props.proposeGroup(r.description);
                }}
              >
                {rungLabel(r, props.site)}
                <span>
                  {r.used
                    ? "in use"
                    : est
                      ? `${in100(est.chance)} in 100 · ${r.projects} projects`
                      : `too few · ${r.resolved} finished, ${r.built} built`}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }
  return (
    <div className="msg bot">
      {who}
      <p className="say">Which projects should I leave out? Tick them here or in the list on the left, and say why.</p>
      <div className="choose">
        <div className="pickwrap">
          {props.waiting.map((p) => {
            const on = props.selected.has(p.id);
            return (
              <label key={p.id} className={`pick${on ? " on" : ""}`}>
                <input
                  type="checkbox"
                  checked={on}
                  disabled={done}
                  onChange={(e) => {
                    const next = new Set(props.selected);
                    if (e.target.checked) next.add(p.id);
                    else next.delete(p.id);
                    props.setSelected(next);
                  }}
                />
                <span>
                  <b>
                    {mw(p.mw)} MW {typeName(p)}
                  </b>
                  <small>
                    <span className="mono">{p.id}</span> · applied {p.applied?.slice(0, 4)}, waited {yrs(p.waited_years)}{" "}
                    years
                  </small>
                </span>
                <span className="c">
                  {mw(p.mw * (p.chance ?? 0))}
                  <small> MW</small>
                </span>
              </label>
            );
          })}
        </div>
        <label className="small muted" htmlFor={`why-${i}`}>
          Why? This goes in the change log.
        </label>
        <input
          type="text"
          id={`why-${i}`}
          value={props.reason}
          disabled={done}
          placeholder="e.g. these have been stuck for years"
          onChange={(e) => props.setReason(e.target.value)}
        />
        <div className="acts">
          <button
            className="btn p sm"
            disabled={done || props.selected.size === 0}
            onClick={() => {
              const ids = [...props.selected];
              props.update(i, { done: true });
              props.setSelected(new Set());
              props.proposeLeaving(ids, props.reason);
              props.setReason("");
            }}
          >
            Show me what would change
          </button>
        </div>
      </div>
    </div>
  );
}
