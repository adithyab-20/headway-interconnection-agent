"use client";

import { useEffect, useRef, useState } from "react";

// Words a newcomer may not know, each with a plain definition one tap away.
const TERMS = {
  queue: [
    "The queue",
    "The waiting list every new power project joins when it asks the grid operator for permission to connect. Each request is studied before it's allowed to plug in.",
  ],
  substation: [
    "Substation",
    "A fenced yard of equipment where power lines meet. It's where a new solar farm, wind farm or battery physically plugs into the grid.",
  ],
  mw: [
    "MW (megawatt)",
    "A measure of how much power a project can send to the grid at once. Large solar farms and batteries are often 100 to 300 MW.",
  ],
  rules: [
    "The 2023 rule change",
    "In 2023 California's grid operator changed how it takes in and studies new requests. Projects that applied under the new rules haven't had time to finish, so their odds can't be known yet.",
  ],
} as const;

export function Term({ term, children }: { term: keyof typeof TERMS; children: React.ReactNode }) {
  const [at, setAt] = useState<{ left: number; top: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!at) return;
    const close = () => setAt(null);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    addEventListener("scroll", close, { passive: true });
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", onKey);
      removeEventListener("scroll", close);
    };
  }, [at]);
  const [title, body] = TERMS[term];
  return (
    <>
      <button
        ref={button}
        className="term"
        aria-expanded={!!at}
        onClick={(e) => {
          e.stopPropagation();
          const r = e.currentTarget.getBoundingClientRect();
          setAt(at ? null : { left: Math.max(8, Math.min(innerWidth - 308, r.left)), top: r.bottom + 8 });
        }}
      >
        {children}
      </button>
      {at && (
        <div className="pop" role="dialog" aria-label={title} style={at} onClick={(e) => e.stopPropagation()}>
          <b>{title}</b>
          {body}
        </div>
      )}
    </>
  );
}
