import type { Metadata } from "next";
import { GITHUB_URL } from "@/shared/brand";
import { Arrow } from "@/shared/icons";

export const metadata: Metadata = {
  title: "Changelog",
  description: "What's changed in Headway, an independent project built around public grid connection data.",
};

const updates = [
  {
    date: "2026-10",
    label: "October 2026",
    title: "Headway is live",
    changes: [
      "Explore California's grid connection queue on an interactive map and see how crowded each substation is.",
      "Compare project types and sizes, estimate the chance of being built and typical wait, and explore past queue outcomes.",
      "Dig into the projects ahead, planned grid upgrades, costs and the past projects used for comparison.",
      "Ask AI questions about a substation and create a written assessment with numbers checked against the source data.",
      "Trace each number to its source rows, adjust which projects count, and accept, reject or rewrite the AI's interpretations.",
    ],
  },
];

export default function ChangelogPage() {
  return (
    <div className="changelog">
      <div className="eyebrow">Built in the open</div>
      <h1>Changelog</h1>
      <p className="lede">Headway is live. Explore California&apos;s grid connection queue with public data and checked AI analysis.</p>
      <a className="link" href={`${GITHUB_URL}/commits/main/`} target="_blank" rel="noopener noreferrer">Full development history <Arrow /></a>
      {updates.map((update) => (
        <article className="changelog-entry" key={update.date}>
          <time dateTime={update.date}>{update.label}</time>
          <h2>{update.title}</h2>
          <ul>{update.changes.map((change) => <li key={change}>{change}</li>)}</ul>
        </article>
      ))}
    </div>
  );
}
