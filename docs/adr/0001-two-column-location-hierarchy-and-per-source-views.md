# Two location columns, and one database view per dataset

**The problem.** The two datasets use the word "region" for two different things. In
LBNL's national dataset, "region" means the grid operator (CAISO, PJM). In CAISO's own file,
it means a planning area inside California (Northern, Fresno). If both went into one
`region` column, `GROUP BY region` would mix big areas with small ones. That would quietly
break the project's main comparison: local figures against national ones.

**The decision.** Store the two levels in separate columns: `iso` for the grid operator, and
`study_region` for the planning area inside it. `study_region` is NULL for LBNL rows,
because LBNL doesn't record planning areas.

LBNL's own "region" field has the same problem one level down. It holds the seven grid
operators, plus "West" and "Southeast", which are not operators at all. They are
catch-all labels for parts of the country with no grid operator, where local utilities run
the grid. Those rows get `iso = NULL`, and the local utility area (from LBNL's `entity`
field) goes in a separate `non_iso_entity` column. That way the mix-up doesn't come back in
a different place.

## What follows from this

CAISO projects appear in **both** datasets. Any total that forgets `WHERE source = ...`
counts them twice, without any error. A database rule can't catch a missing `WHERE`, so we
create two views, `caiso_projects` and `lbnl_projects`, each with its own filter built in.
All analysis functions read a view and never the main table, so a total across both
datasets can't happen by accident. The one deliberate exception is the cross-check between
the two datasets, which reads the main table precisely because it needs both at once.

Analysis functions must be told which dataset to use (`source` has no default). A default
is exactly how a double-count slips in six months later.
