"use client";

// The write-up: the agent's checked Factual Claims and its Judgements, reviewed by a person.
// On screen a Judgement is called an "opinion", the newcomer's word (the design's choice).

import { useState } from "react";
import type { HowWeKnow } from "@/components/Drawer";
import type { Assessment, Claim, Part } from "@/shared/api";
import { AskMark, Chat, Check, No } from "@/shared/icons";

type Judgement = Extract<Claim, { kind: "judgement" }>;

export function FactText({
  parts,
  why,
  asOf,
}: {
  parts: Part[];
  why: (about: HowWeKnow) => void;
  asOf: string;
}) {
  return (
    <>
      {parts.map((p, i) =>
        "text" in p ? (
          <span key={i}>{p.text}</span>
        ) : (
          <button
            key={i}
            className="num t"
            title="See where this comes from"
            onClick={() =>
              why({
                title: p.number,
                say: <>These are the exact projects the lookup returned. Code worked the number out again from them.</>,
                kind: "checked",
                asOf,
                rows: p.rows,
              })
            }
          >
            {p.number}
          </button>
        ),
      )}
    </>
  );
}

export function Writeup(props: {
  site: string;
  asOf: string;
  assessment: Assessment | null;
  writing: boolean;
  problem: string | null;
  write: () => void;
  why: (about: HowWeKnow) => void;
  openAsk: () => void;
  decide: (id: string, d: "agree" | "disagree") => Promise<void>;
  reword: (id: string, text: string) => Promise<void>;
  finalise: () => Promise<void>;
  // The project the page shows now, to say so if the write-up is about another.
  pageProject: { type: string | null; mw: number };
}) {
  const a = props.assessment;
  if (!a) {
    return (
      <div className="doc-card empty-doc">
        <h2>No write-up yet</h2>
        <p>
          The assistant can write a short assessment of this project at {props.site}. It looks the numbers up, code
          checks every one of them against the data before it&apos;s shown, and any opinion waits for you to agree,
          disagree or reword it.
        </p>
        {props.problem && <p className="notice">{props.problem}</p>}
        <button className="btn p" onClick={props.write} disabled={props.writing}>
          {props.writing ? "Writing…" : "Write it"}
        </button>
      </div>
    );
  }
  const opinions = a.claims.filter((c): c is Judgement => c.kind === "judgement");
  const left = opinions.filter((j) => j.decision === "awaiting").length;
  const title = a.project.type ? `${a.project.mw ? `${a.project.mw} MW ` : ""}${a.project.type.toLowerCase()}` : "A project";
  return (
    <div className="writeup">
      <article className="doc-card" aria-label={`${a.project.describe} at ${a.site}`}>
        <h2>
          {title} at {a.site}
        </h2>
        <div className="byline">
          Written by the assistant from the data. Every number was recalculated by code before you saw it.
        </div>
        {(a.project.type !== props.pageProject.type || (a.project.type && a.project.mw !== props.pageProject.mw)) && (
          <p className="notice" style={{ marginTop: 12 }}>
            This write-up is about the project it was written for. The odds now show a different project; reload the
            page to start a write-up for that one.
          </p>
        )}
        <div className="progress">
          {a.final ? (
            <>
              <Check />
              <span>
                <b>Final.</b> Every point has been reviewed.
              </span>
            </>
          ) : left ? (
            <>
              <AskMark />
              <span>
                <b>
                  {left} point{left === 1 ? "" : "s"} need{left === 1 ? "s" : ""} your review.
                </b>{" "}
                Facts are checked by code; opinions need a person.
              </span>
            </>
          ) : (
            <>
              <Check />
              <span>
                <b>All reviewed.</b> You can finalise it.
              </span>
            </>
          )}
          <div className="bar" aria-hidden="true">
            {a.claims.map((c) => (
              <i
                key={c.id}
                style={{
                  flex: 1,
                  background:
                    c.kind === "factual" || c.decision === "agreed" || c.decision === "reworded"
                      ? "var(--ok-mark)"
                      : c.decision === "disagreed"
                        ? "var(--no-mark)"
                        : "var(--ask-mark)",
                }}
              />
            ))}
          </div>
        </div>
        {a.claims.map((c) =>
          c.kind === "factual" ? (
            <div key={c.id} className="stmt">
              <span>
                <Check />
              </span>
              <div>
                <p>
                  <FactText parts={c.parts} why={props.why} asOf={props.asOf} />
                </p>
                <div className="meta">
                  <span className="ok">Fact · checked against the data</span>
                </div>
              </div>
            </div>
          ) : (
            <JudgementView key={c.id} j={c} final={a.final} decide={props.decide} reword={props.reword} />
          ),
        )}
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 18, flexWrap: "wrap" }}>
          <button className="btn p" disabled={a.final || left > 0} onClick={() => void props.finalise()}>
            {a.final ? "Finalised" : "Finalise"}
          </button>
          <span className="muted small">
            {a.final
              ? "No more changes can be made."
              : left
                ? `Review the ${left} remaining opinion${left === 1 ? "" : "s"} first.`
                : "Ready."}
          </span>
        </div>
        {props.problem && (
          <p className="notice" style={{ marginTop: 14 }}>
            {props.problem}
          </p>
        )}
      </article>
      <div className="side-cards">
        <section className="c" aria-labelledby="h-ask">
          <h3 id="h-ask">Questions and changes</h3>
          <p className="small muted" style={{ margin: 0 }}>
            Ask about {a.site} in plain words. Answers are checked before you see them, and you choose which ones join
            the write-up. Changes to what&apos;s counted wait for you to confirm.
          </p>
          <button className="btn p sm" style={{ justifySelf: "start" }} onClick={props.openAsk} disabled={a.final}>
            <Chat /> Open Ask
          </button>
        </section>
        <section className="c" aria-labelledby="h-log">
          <h3 id="h-log">History</h3>
          <ol className="log">
            {a.changes
              .slice()
              .reverse()
              .map((c, i) => (
                <li key={i}>
                  <time className="t">{new Date(c.when).toTimeString().slice(0, 5)}</time>
                  <span>
                    {c.who === "the agent" ? "The assistant" : "You"}: {c.what}
                    {c.why && (
                      <>
                        <br />
                        <span className="muted">&ldquo;{c.why}&rdquo;</span>
                      </>
                    )}
                  </span>
                </li>
              ))}
          </ol>
        </section>
      </div>
    </div>
  );
}

function JudgementView({
  j,
  final,
  decide,
  reword,
}: {
  j: Judgement;
  final: boolean;
  decide: (id: string, d: "agree" | "disagree") => Promise<void>;
  reword: (id: string, text: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(j.text);
  const done = j.decision !== "awaiting";
  const status = {
    agreed: <span className="ok">You agreed</span>,
    disagreed: <span className="no">You disagreed; it won&apos;t be shown</span>,
    reworded: <span className="ok">Reworded by you</span>,
    awaiting: <span className="ask">Opinion · do you agree?</span>,
  }[j.decision];
  return (
    <div
      role="group"
      aria-label={j.text}
      className={`stmt opinion${done ? " done" : ""}${j.decision === "disagreed" ? " rejected" : ""}`}
    >
      <span>{j.decision === "disagreed" ? <No /> : done ? <Check /> : <AskMark />}</span>
      <div>
        {editing ? (
          <>
            <label className="small muted" htmlFor={`rw-${j.id}`}>
              Say it your way
            </label>
            <textarea id={`rw-${j.id}`} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
            <div className="choices">
              <button
                className="btn p sm"
                disabled={!text.trim()}
                onClick={() => {
                  setEditing(false);
                  void reword(j.id, text.trim());
                }}
              >
                Save
              </button>
              <button className="btn q sm" onClick={() => setEditing(false)}>
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            <p>{j.text}</p>
            <div className="meta">
              {status}
              <span>Not checked by code</span>
            </div>
            {!final && !done && (
              <div className="choices">
                <button className="btn sm" onClick={() => void decide(j.id, "agree")}>
                  Agree
                </button>
                <button className="btn sm" onClick={() => void decide(j.id, "disagree")}>
                  Disagree
                </button>
                <button className="btn q sm" onClick={() => setEditing(true)}>
                  Reword
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
