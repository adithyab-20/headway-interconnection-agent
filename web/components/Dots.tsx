// 100 similar projects as dots: built, still waiting, withdrew.

export function Dots({
  built,
  withdrew,
  label,
  className = "dots",
}: {
  built: number;
  withdrew: number;
  label: string;
  className?: string;
}) {
  const waiting = Math.max(0, 100 - built - withdrew);
  const cells = [
    ...Array<string>(built).fill("b"),
    ...Array<string>(waiting).fill("s"),
    ...Array<string>(Math.max(0, 100 - built - waiting)).fill("w"),
  ];
  return (
    <div className={className} role="img" aria-label={label}>
      {cells.map((c, i) => (
        <i key={i} className={c} />
      ))}
    </div>
  );
}

export function OutcomeKey() {
  return (
    <div className="key">
      <span>
        <i style={{ background: "var(--t3)" }} />
        built
      </span>
      <span>
        <i style={{ background: "var(--sand)" }} />
        withdrew
      </span>
      <span>
        <i style={{ boxShadow: "inset 0 0 0 1.5px var(--sky-edge)" }} />
        still waiting
      </span>
    </div>
  );
}
