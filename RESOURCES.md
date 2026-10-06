# Interconnection Agent Resources

## Reference documents

- [Build plan](docs/specs/build-spec.md)
  The full design: data sources, how each number gets checked, how the agent is tested, and
  the order to build things in. Read before planning work.
- [Plan for the first working version](docs/specs/vertical-slice.md)
  What the first end-to-end version includes and where its tests attach. Use it to decide
  whether a ticket belongs in the current scope.
- [Word meanings](CONTEXT.md)
  What substation, crowding (saturation), queue-entry year (vintage), resolved withdrawal
  rate, and provenance mean here. Use when naming tables, functions, and outputs.
- [Decision 0001](docs/adr/0001-two-column-location-hierarchy-and-per-source-views.md)
  Why location is two columns, and why analysis must read each dataset through its own view.
- [Decision 0002](docs/adr/0002-rates-are-cohorted-by-vintage.md)
  Why rates are worked out per queue-entry year, and why wait times look better than reality.
- [Decision 0003](docs/adr/0003-claims-are-generated-structured-not-parsed-from-prose.md)
  Why the model returns structured claims, how each number is checked, the all-rows check,
  and what the checks can't prove.

## People to ask

- Pull-request reviews and issue discussions on this repo
  Use them to challenge data mappings, expected-answer SQL, and domain assumptions before they
  become hard to change.
