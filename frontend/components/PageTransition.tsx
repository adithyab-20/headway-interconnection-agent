import { ViewTransition } from "react";

// How a page arrives and leaves: sliding forward or back when the link says which way it
// goes (into a substation, back to the map), crossfading otherwise.
const MOVE = { "page-forward": "page-forward", "page-back": "page-back", default: "page-fade" };

export function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <ViewTransition enter={MOVE} exit={MOVE} default="none">
      {children}
    </ViewTransition>
  );
}
