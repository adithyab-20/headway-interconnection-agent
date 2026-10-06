# A map point comes from OpenStreetMap or a cited public document, never a guess

**Status:** accepted. Replaces the "OpenStreetMap or county" rule in
[Where substation locations come from](https://github.com/adithyab-20/interconnection-agent/issues/37).

**The problem.** OpenStreetMap draws most substations, but names only about a third of them.
Matching by name alone left about 30% of the MW waiting in CAISO's queue with no point on the
map, including some of the biggest substations: Trout Canyon, Manning, Tranquillity. Several
of those aren't built yet, so no map can show them, yet their planned spot is public.

**The decision.** Each site's point comes from one of these, in order. The table that holds
them (`src/interconnection_agent/places/positions.csv`) says which one answered, in
`positioned_by`, and names the exact source in `source`:

| `positioned_by` | Accepted when |
|---|---|
| `openstreetmap` | OpenStreetMap names a substation with this site's name, in the projects' own or a neighbouring county. A namesake further away is flagged for review, not used. |
| `document` | A public document fixes the spot without judgement on our part: coordinates, a parcel, or a named road junction with a distance and direction. Where OpenStreetMap has drawn a substation there, the point is that shape. |
| `planned` | The same, for a substation that isn't built yet: the point is where the filing says it will go. |
| `county` | Nothing above answers. No point; the place falls back to its county, and the product says so. |

The documents used are utilities' construction notices to the CPUC, environmental reviews,
CAISO notices and federal land-use plans. Each row quotes what it relies on, so anyone can
check it.

**What this gives.** 88% of waiting MW has a point, up from 70%. The rest is listed under its
county.

## A description that fits several places is not resolved

"A switching station on the Gates-Midway line" fits many spots. If a document doesn't single
out one place, the site stays at county level. Picking the likeliest shape would be a guess
presented as a fact, and the product's promise is that every number and every point can be
traced.

## Only sources that can be shown publicly

A source is used only if its terms allow showing its points on a public site with credit:
OpenStreetMap (ODbL, credited on the map and in the README) and public documents (facts
about where something is, each cited). Datasets whose owners have withdrawn them from public
access, or which need a login or a data-use agreement, are not used, even where a copy can
still be found online.

## Consequences

- The map needs two displays besides a dot: "somewhere in this county" for unplaced sites,
  and "planned, not yet built" for planned ones. Settled at the start of the map-app ticket
  ([#45](https://github.com/adithyab-20/interconnection-agent/issues/45)).
- `positions.csv` stays under the ODbL as a whole; the document rows are cited facts and
  don't change that.
- New public documents can move a site from `county` to `document` or `planned` at any
  time. Each one is added by hand, never drafted by a script.
