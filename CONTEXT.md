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

**Saturation**:
How crowded a substation is: MW still waiting to connect there, compared with MW that has
actually been connected there before. Needs CAISO's own file (`caiso_raw`); LBNL's data
doesn't have the detail.

**Withdrawal**:
A project leaving the queue without ever being connected. This is the most common outcome:
most projects in the queue drop out.

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

**Assessment**:
One complete answer the agent gives about a site: a set of claims, each checked, turned
into readable text.

**Claim**:
One factual statement in an assessment, carrying the numbers it states, the rows they came
from, and whether the check passed.
_Avoid_: statement, fact, finding
