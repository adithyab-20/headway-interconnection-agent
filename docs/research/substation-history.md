# Research: more history per substation

*Research note, October 2026 (ticket #58, planning map #44). Sentences marked **Inference** are
my own reasoning. Everything else is either measured here or attributed to a linked source.
"Measured here" figures come from throwaway scripts (not committed) run on
`data/publicqueuereport.xlsx` (CAISO's report dated 2026-07-24), the LBNL national file
(`LBNL_Ix_Queue_Data_File_thru2025.xlsx`), CAISO files fetched on 2026-10-05 and one
OpenStreetMap download made on 2026-10-05. Tested code does not reproduce them.*

"Past outcomes" means finished projects: **built** plus **withdrawn**. CAISO's report has 249
built and 1,759 withdrawn, so 2,008 in total. "Waiting" means still in the queue (270 projects).

## Summary

- **Grouping our own spellings is the cheapest big win.** Substations with ≥5 past outcomes go
  from **15 to 59** with an automatic rule, or **77** after about half a day of review. Waiting
  projects with ≥5 local outcomes go from **48 to 110–126** (of 270).
- **Two policy choices add more:** all voltages at one site as one substation (**68**), and line
  taps counted at both end substations (**136**). Line taps are 34% of past outcomes.
- **LBNL does not clean spellings** (it copies CAISO's text in 2,276 of 2,278 rows), but it adds
  the 2023 application batch missing from CAISO's main report: **482 early withdrawals**.
- **CAISO publishes a bottleneck spreadsheet** (93 shared overloaded lines or transformers, 906
  connection points); **57 have ≥20 past outcomes**. Its lists change from year to year.
- **The rest add little:** EIA-860 has no substation names, the study reports need a login, one
  third-party site forbids reuse, and OpenStreetMap circles place only 37% of past outcomes.

## 1. How much would grouping our own data add?

**Method (measured here).** I loaded all three sheets, 2,278 rows, all with station text. I ran
the existing normalizer (`poi/normalize.py`). Then I added a stricter rule:

- drop words such as "Substation", "Sub", "Switchyard", "Switching Station" and "Bus";
- drop utility prefixes and the text in brackets;
- keep the voltage, treating 220 kV and 230 kV as one level (SCE writes 220 for what others
  write as 230).

Then I re-ran the existing suggestion method (`scripts/propose_poi_aliases.py`: rapidfuzz
token-sort score ≥ 88, greedy) over **all** spellings, not just waiting ones.

**Spellings.** All three sheets hold **1,482 distinct spellings** after the normalizer.

- 171 are already in the reviewed table.
- The rule collapses all 1,482 into **1,150 groups** with no review. To check the rule, I
  compared it with the reviewed table's 171 spellings. It disagrees in only 4 places. It
  merges "Schulte 115 kV" with "Schulte Switching Station 115 kV Bus", which the reviewer kept
  apart. It also fails to join 3 typos ("Vota-South", "Midway Temblor", "portion of
  Eldorado").
- The fuzzy step then **proposes 118 more merges**:
  - 25 differ only in voltage (Los Banos 70/230/500 kV). One policy decision covers all of them.
  - 93 need a person. Real ones include Tranquility/Tranquillity, Mohave/Mojave and
    Bellota/Belotta. Wrong ones include Calcite/Caliente, Oakland C/Oakland J and Valley
    Springs/Spring Valley. Reading the first 60, about 1 in 8 was wrong.
- The remaining ~900 groups are mostly single spellings with one or two outcomes. They have
  nothing to merge.

**Review effort (Inference).** About 93 yes/no decisions at a minute each. Add a skim of the 181
rule groups with more than one spelling (a sample of 45 had at most two doubtful ones, e.g. "GWF
Hanford" vs "Hanford Switchyard") and the two policy decisions below. In all, about **half a
day**. The rule must stay offline, feeding suggestions into `aliases.csv`, never resolving names
at runtime.

**Effect on history (measured here).** Counts are per group, past outcomes = built + withdrawn.

| Grouping | ≥5 past | ≥10 | ≥20 | ≥3 built | Waiting projects whose group has ≥5 |
|---|---|---|---|---|---|
| Today: reviewed table only | 15 | 5 | 2 | 7 | 48 (17% of waiting MW) |
| Exact lower-case text | 27 | 6 | 0 | 11 | 35 |
| Automatic rule (220 = 230 kV) | 59 | 19 | 4 | 14 | 110 (37% MW) |
| Same, 220 and 230 kept apart | 55 | 18 | 4 | 14 | 95 |
| Rule + all fuzzy suggestions accepted (upper bound) | 77 | 22 | 5 | 16 | 126 (49% MW) |
| Rule, all voltages at a site as one | 68 | 29 | 8 | 15 | 144 (57% MW) |
| Previous row + line taps counted at both end substations | 136 | 61 | 20 | 31 | 187 |

(The ticket's earlier figure of 26 for exact lower-case grouping differs from my 27 by one; the
counting was probably slightly different.)

**Line taps.** 681 of the 2,008 past outcomes (34%) are at spellings that name a power line
("Midway-Wheeler Ridge 230 kV line"), measured with a simple pattern for "line", "tap" or
"A-B". **Inference:** a project tapping a line between A and B shares much of its fate with A
and B. Counting it toward both is the largest single gain in the table, but it is a modelling
choice the owner should make on purpose.

**Is LBNL's `poi_name` cleaner? No.** Matching LBNL `q_id` to CAISO "Queue Position" pairs all
2,278 CAISO rows. In 2,276 of them, `poi_name` is CAISO's text character for character. The
other two differ only by a broken character encoding. Both sources give 1,482 distinct
spellings. LBNL's codebook says only that the field "may be a substation name or transmission
line tap". So it cannot speed up grouping.

## 2. Other public sources

**LBNL adds the 2023 application batch (measured here).** LBNL has 2,868 CAISO rows, which is
590 more than CAISO's main report. All 590 are from the 2023 application batch (LBNL `cluster`
= "Cluster 15"). 482 are withdrawn (420 in 2024, 62 in 2025) and 108 were waiting at the end of
2025. CAISO's main report holds no 2023-batch project at all. CAISO lists that batch in a
[separate report](https://www.caiso.com/library/interconnection-queue-reports) dated
2026-07-16 (file `cluster-15-interconnection-requests.xlsx`). It has 86 waiting and 84 withdrawn
rows, all present in LBNL. CAISO says 541 applications came in during 2023, 255 re-applied
complete, and 177 went on after scoring
([CAISO scoring summary, p. 4](https://www.caiso.com/documents/summary-of-cluster-15-intake-scoring-results.pdf)).

Adding LBNL's 482 withdrawals to the automatic rule grouping raises substations with ≥5 past
outcomes from 59 to **93** (≥10: 19 → 26). **Inference:** most of these projects dropped out
when CAISO screened and ranked applications, before any engineering work. That is weaker
evidence about a substation than a withdrawal after the operator's engineering studies. Keep
them as a separate kind of outcome. LBNL's file is under CC BY 4.0 (see `data/README.md`). It
must be credited.

**Older archived CAISO reports.** The Internet Archive was unreachable from here, and CAISO's
[library](https://www.caiso.com/library/interconnection-queue-reports) lists no old editions.
Today's report reaches back to 1999–2000 applications, and every older CAISO row in LBNL is also
in it. **Inference:** CAISO keeps old withdrawals, so old reports would add few projects. Not
confirmed.

**CAISO's engineering study reports** (the operator's studies of what grid upgrades a batch of
projects needs, with costs). The per-area reports and per-project appendices go on the
login-only Market Participant Portal, the per-project ones redacted
([CAISO notice](https://www.caiso.com/notices/generator-interconnection-applications-redacted-individual-generator-interconnection-appendix-a-reports-for-cluster-14-phase-2-posted-on-the-iso-market-participant-portal);
[generator interconnection page](https://www.caiso.com/generation-transmission/generation/generator-interconnection)).
They are not usable for a public product without permission. Not inspected.

**CAISO's yearly report on sharing out spare grid capacity**
([2025, PDF](https://www.caiso.com/documents/2025-transmission-plan-deliverability-allocation-report.pdf))
lists projects behind each bottleneck, but only unbuilt ones and only as PDF tables. No outcomes.

**EIA-860.** The plant form asks for "grid voltage at the point(s) of interconnection" (up to
three) and the owner of the lines the plant connects to. It also asks for the market price-node
name. It does not ask for a substation name or a queue number
([EIA-860 form, Schedule 2](https://www.eia.gov/survey/form/eia_860/proposed/form.pdf);
[EIA-860 data](https://www.eia.gov/electricity/data/eia860/)). **Inference:** it could
confirm built projects and give plant coordinates, but it records no withdrawals and has no
substation to join on, so it adds no outcomes per substation.

**Third-party datasets.**

- The open-source *gridstatus* library is BSD-3 licensed
  ([repo](https://github.com/gridstatus/gridstatus)). For CAISO it downloads the same current
  report with no date option
  ([source](https://raw.githubusercontent.com/gridstatus/gridstatus/main/gridstatus/caiso/caiso.py)).
  Nothing new.
- *Interconnection.fyi* forbids "bulk downloading, scraping, or redistribution" without consent
  ([terms](https://www.interconnection.fyi/terms)). Not usable.
- *LBNL*: see above. It is the only third-party source that adds rows.

## 3. Grouping substations that share a fate

**CAISO's bottleneck spreadsheet.** CAISO published "Attachment B1 v8 Constraint Mapping 2024"
([library page, 2024-10-17](https://www.caiso.com/library/transmission-capability-estimate-inputs-for-cpuc-integrated-resource-plan-aug-29-2024)).
It is an Excel grid of connection points against bottlenecks. A bottleneck here is a line or
transformer that projects at many substations would overload. The grid has a tick wherever a
substation sits behind one. Measured here:

- 906 connection-point rows and 93 bottlenecks;
- a median of 17 connection points per bottleneck (range 1–265);
- each connection point sits behind a median of 3 bottlenecks. They overlap, so they are nested
  areas, not a map split into pieces.

Matching by the automatic rule name places 205 of 270 waiting projects (75% of waiting MW), 156
of 249 built and 907 of 1,759 withdrawn. **Inference:** the misses are mostly older and smaller
local connection points. Bottlenecks with ≥5 past outcomes: **84 of 93**; ≥10: 71; ≥20:
**57**; ≥3 built: 56.

A fallback order (measured here): use the substation's own history if it has ≥10 past outcomes
(57 waiting projects); otherwise the *smallest* bottleneck around it with ≥20 (149 more; median
32 connection points, quartiles 20–51); 64 waiting projects are not in the spreadsheet.

**The spreadsheet is not stable across years (measured here).** The 2023 edition was a PG&E-only
Excel list, plus PDF diagrams for southern California
([2023 library page](https://www.caiso.com/library/transmission-capability-estimate-inputes-for-cpuc-integrated-resource-plan-jul-05-2023)).

- PG&E had 63 bottlenecks in 2023 and 56 in 2024. Only 48 names appear in both.
- Of 147 PG&E connection points in both years, only 55 sit behind exactly the same shared
  bottlenecks.

**Inference:** freeze one dated edition as the area map, and record which edition was used. Do
not try to track it year by year.

**The queue's own "allocation group" column is not a place.** Groups A–D are priority classes
based on contract status ("executed power purchase agreements", "shortlisted", and so on)
([2025 sharing-out report, p. 5](https://www.caiso.com/documents/2025-transmission-plan-deliverability-allocation-report.pdf)).
The "study region" column has only about 11 large areas, and 105 of the 249 built rows leave it
blank. It is too coarse to count as local.

**County (measured here).** 99 counties hold past outcomes: 45 have ≥5, 35 have ≥10, 20 have ≥20,
and 21 have ≥3 built. 260 of 270 waiting projects are in a county with ≥5. The county is in
every row. But it is the project's site, not the substation's
([substation-locations note](https://github.com/adithyab-20/interconnection-agent/blob/research/substation-locations/docs/research/substation-locations.md)).

**Distance circles (measured here).** I fetched 1,854 named OpenStreetMap substations in CA, NV
and AZ through an [Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API) mirror. I placed
a substation name only if every OSM feature with that name lies within 3 km of the others.

- 172 names could be placed, holding 747 of 2,008 past outcomes (37%). Line taps hold 681, names
  not found hold 514 and ambiguous names hold 66.
- 141 of 270 waiting projects can be placed.

| Circle radius | Placed substations with ≥5 / ≥10 / ≥20 past (of 172) | Waiting placed projects with ≥20 nearby |
|---|---|---|
| 10 km | 65 / 27 / 9 | 42 of 141 |
| 20 km | 103 / 65 / 24 | 58 of 141 |
| 30 km | 133 / 95 / 54 | 73 of 141 |
| 50 km | 154 / 136 / 98 | 90 of 141 |

Licence: ODbL, credit required (see the substation-locations note).

**Which grouping? (Inference.)** Bottleneck areas: membership is defined by the overloaded
equipment itself, and they give ≥20 past outcomes for most waiting projects at about 32
connection points. Distance circles cover under half the projects and ignore grid wiring.
County is the last fallback.

## Recommendation

1. **Group all spellings offline, then review.** Run the automatic rule plus the fuzzy
   suggestions over all three sheets. A person accepts them into `aliases.csv`. Expected gain:
   substations with ≥5 past outcomes go from 15 to 59–77, and waiting projects with ≥5 local
   outcomes go from 48 to 110–126. Effort: about half a day of review, plus extending the script
   to read all sheets.
2. **Make two policy decisions:** is 220 kV the same as 230 kV, and are all voltages at one site
   one substation? Gain: up to 68 substations with ≥5, and 144 waiting projects covered. Effort:
   one decision, written down as a decision record in `docs/adr/`.
3. **Ingest the 2023 batch.** Read CAISO's separate 2023-batch report (86 waiting, 84 withdrawn,
   currently missing from the product). Optionally add LBNL's further screening-stage
   withdrawals, flagged as a separate kind of outcome. Gain: 59 → 93 substations with ≥5 if all
   are counted. Effort: a small reader for one more sheet format.
4. **Fall back to bottleneck areas.** Load one frozen edition of CAISO's 2024 bottleneck
   spreadsheet. Use the order: own substation (≥10) → smallest bottleneck area with ≥20 →
   county. Gain: about 206 of 270 waiting projects get ≥10–20 comparable outcomes. Effort: a
   reader plus the same name matching. The edition date must be shown with the number.
5. **Decide how to treat line taps.** Counting them at both end substations doubles the
   substations with ≥5 (68 → 136). Effort: small, once item 1 exists.
6. **Do not pursue** EIA-860, the third-party sites, the login-only study reports or distance
   circles for now.

## Open questions

- Should screening-stage withdrawals from the 2023 batch count as outcomes, or be shown
  separately?
- Should a line-tap project count toward both end substations, or form its own group?
- Is a bottleneck area "local" enough to show next to a substation, and how should the
  fallback be explained on the page?
- Will CAISO publish a 2025/2026 edition of the bottleneck spreadsheet, and in what form? I
  found none dated after October 2024.
- Do archived CAISO reports hold withdrawals that today's report has dropped? This could not be
  checked here, because the Internet Archive was unreachable.
