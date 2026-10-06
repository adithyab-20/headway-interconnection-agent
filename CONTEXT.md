# Interconnection Due-Diligence

Judges how risky it will be to connect a proposed power plant to the grid. Every number is
backed by specific rows of public queue data, and anything that can't be backed that way
is labelled as such.

## Language

### Grid and geography

**ISO**:
An independent system operator: the organisation that runs the grid in a large area and
keeps its interconnection queue. Examples: CAISO (California), PJM, MISO, ERCOT, SPP, NYISO,
ISO-NE. This is the widest area a question can be about.
_Avoid_: RTO, market, region (see Study Region)

**Study Region**:
A smaller planning area inside one ISO, which the operator uses to organise its studies, for
example CAISO's "Northern", "Fresno", and "Eastern". Each one sits entirely inside a single
ISO. Only CAISO's own file (`caiso_raw`) records this.
_Avoid_: region, zone, area

**Non-ISO Entity**:
The local utility area that runs the grid where there is no ISO. LBNL lumps these into
"West" and "Southeast". These are not ISOs and must never be stored as one.
_Avoid_: non-ISO region

**POI (Point of Interconnection)**:
The substation or power line where a project physically connects to the grid. Stored twice:
`raw_poi` (the operator's text, exactly as typed) and `normalized_poi` (after spellings are
grouped).
_Avoid_: interconnection point, station, tie-in

**Site**:
One substation, under the single name all its spellings are grouped to ("Birds Landing").
Two unrelated substations that share a name are kept as two sites, the second named with its
county ("Mesa (Los Angeles County)").
_Avoid_: station, location

**Place**:
One voltage section of a site ("Birds Landing 230 kV"): what a project is linked to, and the
unit history is counted at. A project partway along a power line is linked to the places at
both ends of the line.
_Avoid_: node, bus

**Map Position**:
A site's point on the map, and what it comes from (`positioned_by`): a substation
OpenStreetMap names, or a cited public document. A site with neither falls back to its
county and has no point. Never guessed. See `docs/adr/0004-where-map-points-come-from.md`.
_Avoid_: location, coordinates (on their own)

**Planned Substation**:
A substation the operator or a utility has approved but not yet built. It can have a map
position, taken from the filing that says where it will go, always shown as planned.
_Avoid_: future substation, proposed substation

**Bottleneck**:
An overloaded power line or transformer that limits how much new generation the places
behind it can add, from CAISO's list. Its **Room Left** is the MW still available behind it;
its cost to add room is the price of the next upgrade per kW it adds.
_Avoid_: constraint, deliverability constraint

**Planned Upgrade**:
A grid upgrade the operator has approved, with its expected finish date and cost range, linked
to the places it's at. Paid by all electricity customers, never by the projects nearby.
_Avoid_: network upgrade, transmission project

### Project lifecycle

**Project**:
One request to connect to the grid. Identified by which dataset it came from plus that
dataset's own ID (`source`, `native_id`).

**Energization**:
The date a project actually started operating. Not the same as the *proposed* online date,
which is a forecast and is often wrong.
_Avoid_: completion, COD, going live

**Time-to-Energization**:
How long a project waited from joining the queue to starting operation
(`actual_online_date − q_date`). It can only be measured for projects that finished, so it
looks better than reality: projects still stuck in year nine aren't counted. This warning
is returned together with the number, so it can't be left out.

**Chance of Reaching Operation**:
For projects like a given one (same technology, similar size), the share expected to reach
operation within N years of joining the queue. Projects still waiting count for the years
they have been seen, never as successes or failures. Always shown with a likely range and
the number of past projects behind it, and labelled with the queue rules the history comes
from.
_Avoid_: success rate, completion rate (unqualified)

**Comparison Group**:
The past projects a new project is compared with to work out its Chance of Reaching
Operation. Chosen as the most similar group that still has enough past projects to trust
(by type, then size, then local area); the user can make it narrower or broader.
_Avoid_: cohort, peer set, "projects like yours" (informal)

**Typical Wait**:
The time by which half of the projects that eventually reach operation have done so, read
from the same calculation as the Chance of Reaching Operation.

**Realistic MW Ahead**:
The MW waiting at a substation, with each waiting project counted only by its chance of
still being built given how long it has already waited. A crowded substation full of old,
stuck projects has far fewer realistic MW ahead than its raw total. Only projects that
applied under the old rules are counted: the old-rules history can't give a chance for the
2023 batch, so its waiting MW is always shown beside this number as its own figure, at full
MW, labelled "chance not known". The two are never added together.
_Avoid_: effective queue, adjusted MW

**Backtest**:
Replaying the history as it stood on past cut-off days, predicting each waiting project's
chance of being built in the next five years, and comparing with what happened. What it
reports is calibration (of the projects given about 20%, were about 20% built?), not
accuracy. The automatic checks run on every change fail if it gets worse than the
accepted level.

**Saturation**:
How crowded a substation is: MW still waiting to connect there, compared with MW that has
actually been connected there before. Needs CAISO's own file (`caiso_raw`); LBNL's data
doesn't have the detail.

**Withdrawal**:
A project leaving the queue without ever being connected. This is the most common outcome:
most projects in the queue drop out.

**Batch**:
The group of requests the operator took in and studied together (`batch`), for example the
2023 batch (`C15`). That batch entered under the new rules, so it's kept out of the
old-rules history and reported as a fact of its own.
_Avoid_: cluster, window

**Furthest Step**:
How far a project got through the operator's process before it was built, withdrew or is
now: no study done, first study done, second study done, or agreement signed
(`furthest_step`).
_Avoid_: phase, stage

**Vintage**:
The year a project joined the queue (the year of `q_date`). Every rate is worked out per
vintage, because older projects have had more time to reach an outcome.

**Resolved**:
A project that has reached a final outcome: connected or withdrawn. Projects still waiting
are *unresolved*, and are left out of both the top and the bottom of a rate.

**Resolved Withdrawal Rate**:
For one vintage, `withdrawn / (withdrawn + operational)`, reported together with how many
projects are still waiting. A single rate over all years at once comes out too low, so it
isn't used.
_Avoid_: withdrawal rate (unqualified)

### Where numbers come from

**Source**:
Which dataset a row came from: `caiso_raw` (CAISO's own weekly spreadsheet) or `lbnl`
(Berkeley Lab's cleaned-up national dataset). CAISO projects appear in **both**, so the two
are never added together.

**Provenance**:
The exact source rows a result was worked out from: the source, each row's `native_id`, and
the values used. Every analysis function returns this together with its numbers.

**Lookup**:
One query the agent runs (`tool_call_id`), saved in a log with every row it returned. A
number in a Factual Claim names the lookup it came from, and must use exactly the rows that
lookup returned.
_Avoid_: query (on its own), tool call

**Assessment**:
One complete answer the agent gives about a site: a set of claims, each checked, turned
into readable text.

**Claim**:
One statement in an assessment. Every claim is either a Factual Claim or a Judgement.
_Avoid_: statement, fact, finding

**Factual Claim**:
A claim that states numbers worked out from specific source rows. Code checks it against
the data; a person never needs to.

**Judgement**:
A claim that interprets the numbers (a likely cause, whether projects are comparable, a
recommendation). Code cannot check it, so a person approves it, rejects it, or rewrites it.
_Avoid_: opinion, qualitative claim

**Adjustment**:
A change a person makes to what goes into an assessment, such as excluding a project with a
reason or narrowing which projects count. The affected numbers are then worked out again
and checked again. Numbers themselves are never typed over.
_Avoid_: override, manual edit
