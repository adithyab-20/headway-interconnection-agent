// How numbers are shown, the same way everywhere on the site.

/** MW to the nearest 10, like the checker's margin. */
export const mw = (v: number): string =>
  v > 0 && v < 10 ? "under 10" : (Math.round(v / 10) * 10).toLocaleString("en-US");

export const pct = (v: number): string => {
  const p = v * 100;
  return p > 0 && p < 1 ? `${p.toFixed(1)}%` : `${Math.round(p)}%`;
};

/** A share as "N in 100". */
export const in100 = (v: number): number => Math.round(v * 100);

export const yrs = (v: number): string => v.toFixed(1).replace(/\.0$/, "");

export const dateLong = (iso: string): string =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

export const plural = (n: number, one: string, many = `${one}s`): string =>
  `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;

// Realistic MW ahead, in four plain classes.
export const BREAKS = [300, 1000, 2000];
export const CLASS_LABEL = ["under 300", "300–1,000", "1,000–2,000", "2,000+"];
export const classOf = (v: number): number => BREAKS.filter((b) => v >= b).length;
export const classVar = (k: number): string => ["var(--t1)", "var(--t2)", "var(--t3)", "var(--t5)"][k];
