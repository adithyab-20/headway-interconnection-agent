# Where public grid-upgrade cost data comes from

Research for issue #60 (part of #44). Researched 2026-10-05. Every number says how it was measured; my own reasoning is marked **Inference**.

## Summary

- **Berkeley Lab has no California costs.** Its project-level cost files cover other regions. Its own slides say the California grid operator (CAISO) "does not disclose project-level interconnection costs".
- **CAISO's yearly transmission plan is public and lists upgrades by substation name, with cost and finish year.** The owner's example is real: "Newark 230/115 kV Bank Upgrade", $63M, in service 2032. But these upgrades are paid by all electricity customers and are mostly driven by demand growth. They are not a project's own cost, so they must be labelled that way.
- Name-matching on our 164 reviewed substation names (all used by waiting projects): 38 match an upgrade approved in the 2025-26 plan, and 91 match some approved upgrade still being built. The 38 cover 62 of 270 waiting projects.
- **For "how expensive is it to connect here", the best source is a different CAISO spreadsheet.** For each congested area it gives the cost of the next upgrade and how many MW of new projects that upgrade makes room for. That gives about $11-2,506 per kW (median $133) for 63% of waiting projects.
- **Signed connection agreements filed with the federal energy regulator (FERC) are public, unredacted and show real project costs**, but only a minority are filed, and extraction is manual.
- Everything recommended is public CAISO material that may be reused with credit.

## Words used in this note

- **Upgrade**: new or bigger lines, transformers or breakers the grid needs.
- **Connection agreement**: the signed contract between a project, the local utility and CAISO listing the work and its cost.
- **Full-capacity status** ("deliverability"): permission for a project's output to count toward California's supply on the hottest days. Areas run out of room for this first.
- **Study reports**: CAISO's engineering studies that set each project's costs. They are on a members-only portal and out of scope.

## 1. Berkeley Lab (LBNL) cost data

LBNL publishes project-level cost spreadsheets for MISO, PJM, SPP, ISO-NE and NYISO, and for PacifiCorp, Bonneville and Duke ([LBNL interconnection costs](https://emp.lbl.gov/interconnection_costs)). CAISO is excluded: LBNL says CAISO does not disclose project-level costs (slide 9, [2023 summary briefing](https://eta-publications.lbl.gov/sites/default/files/berkeley_lab_interconnection_cost_webinar.pdf)). The February 2026 report's text says its earlier work included CAISO (p. 6, [report](https://eta-publications.lbl.gov/sites/default/files/2026-02/lbnl_2026.02.23_ba_interconnection_costs.pdf)). But its data file lists the earlier regions as "five ISOs (MISO, SPP, PJM, NYISO and ISO-NE)" (sheet "Costs by Market Structure", [data file](https://eta-publications.lbl.gov/sites/default/files/2026-02/ba_costs_2024_clean_data.xlsx)). **Inference:** the CAISO mention is a slip.

**Measured** (file downloaded to the scratchpad): 8 of its 2,104 rows are in California. All 8 are PacifiCorp projects in Siskiyou County, outside the CAISO grid (State and BA columns). None matches our queue. LBNL's queue file in `data/` has no cost columns (sheet "03. Complete Queue Data"). The cost files carry only a disclaimer and a U.S. Government copyright notice, not CC-BY (Introduction sheets). LBNL says collecting costs by hand took 400-500 person-hours per region (slide 9).

## 2. Signed connection agreements filed with FERC

**Only some are filed.** An agreement on the standard form "need not be filed" with FERC. It is only reported in a quarterly report ([Order 2003-A](https://www.ferc.gov/sites/default/files/2020-04/order2003-a.pdf), para. 201). Filed ones are non-standard, unsigned or amended.

**Count.** I searched [FERC eLibrary](https://elibrary.ferc.gov/eLibrary/search) for tariff filings that mention a generator connection agreement, from 2010 to 2026. Edison: 190 (72 amendments, 22 terminations). PG&E: 35. SDG&E: 14. For comparison, our queue file has 518 projects with a signed ("Executed") agreement: 218 waiting, 238 built and 62 withdrawn. Of these, 250 are with PG&E. **Inference:** filings cover about a quarter of signed agreements at most, and few PG&E ones. None of the 239 filings had a file marked privileged or grid-security (checked access codes and file names).

**Examples** ($/kW = total ÷ net MW in our queue file):

| Project (queue no.) | Substation | Cost in agreement | Net MW | $/kW | Source |
|---|---|---|---|---|---|
| Elion Energy Storage (Q2064), waiting | Antelope 220 kV | $17.75M | 300 | 59 | [ER25-3227](https://elibrary.ferc.gov/eLibrary/filelist?accession_number=20250819-5080), App. A §5 |
| Sapphire Solar (Q1764), waiting | Red Bluff 220 kV | $2.66M own facilities (shared part paid by Q643AE) | 117 | 23 | [ER24-1635](https://elibrary.ferc.gov/eLibrary/filelist?accession_number=20240328-5111), App. A §5 |
| Whale Rock Energy (Q1749), **withdrawn 2025** | Caliente 230 kV | $5.00M grid upgrades + $3.33M connection equipment | 299.65 | 28 | [ER24-2705](https://elibrary.ferc.gov/eLibrary/filelist?accession_number=20240805-5152), App. G |

Each agreement prints the queue number on its title page. One standard-form agreement, [EdSan 1 and 2 at Windhub](https://sanjosecleanenergy.org/wp-content/uploads/2021/02/Terra-Gen.Edwards.LGIA_.PUBLIC.pdf) ($8.0M for 300 MW and $1.7M for 500 MW), was not on FERC at all. I found it on a power buyer's website.

**Effort.** The cost tables sit around pages 108-113 of 100+ page PDFs, and the layouts differ by utility. **Inference:** about 1-2 hours per agreement by hand. **Inference on licence:** these are public federal records and the figures are facts, so citing them should be low-risk. I found no explicit FERC reuse statement. **Caveat:** in CAISO a developer is usually repaid for wider grid upgrades once its project runs ([Brattle scorecard](https://www.brattle.com/wp-content/uploads/2024/03/Generator-Interconnection-Scorecard.pdf), p. 35).

## 3. CAISO's public transmission plan

### 3.1 What it lists, and where

The latest plan is the [2025-2026 Transmission Plan](https://www.caiso.com/documents/board-approved-2025-2026-transmission-plan.pdf), approved 19 May 2026. The PDF is dated "Updated … August 27, 2026" and has 182 pages. Every page is marked "CAISO Public". It has three layers:

| What | Where | Fields |
|---|---|---|
| Summary tables of newly approved upgrades (38 projects, $6.7B) | Tables 2-3, 2-4, 2-5 (PDF pp. 100-102), 3-2 (p. 117), 4-6 (p. 135) | ID, name, utility, planning area, cost ($M). **No finish year.** |
| One write-up per upgrade | Chapter 2-4 sections headed "Estimated Cost & In-Service Date" (32 found) | cost range and finish year in prose |
| One fact sheet per upgrade | [Appendix H - Projects](https://www.caiso.com/documents/board-approved-2025-2026-transmission-plan-appendix-h-projects.pdf) | Name, Description, Type, Need date, Expected in-service date, Interim solution, Project cost (range) |
| Older upgrades still being built | Tables 8-2, 8-3 (PDF pp. 173-176) | name, utility, finish year. **No cost.** |

**The owner's example checks out.** "2526-R-12 Newark 230/115 kV Bank Upgrade, PG&E, GBA, $63M" is in Table 2-4 (PDF p. 101). Section 2.3.2.11 (PDF p. 65) says it replaces transformer #11 at Newark. It gives "a cost estimate of $31.3 million - $62.6 million and an estimated in-service date of 2032". The need is customer demand in San Jose ("an overload on Transformer Bank #11 by 2030"). The table figure is the top of the range (also true for Metcalf, $405M from $270-405M, and DeAnza, $260M from $130-260M). Suggested wording: *"Newark substation: a transformer upgrade estimated at $31-63 million is planned for 2032 (CAISO 2025-26 Transmission Plan)."*

### 3.2 Can it be extracted reliably?

- **Appendix H is the easy route.** `pdftotext -layout` plus a short label parser read 33 fact sheets. 31 came out with both cost and finish year. The other two (Lugo 230 kV breaker upgrade and Devers 230 kV upgrade) are blank in the PDF itself. Their costs, $5M and $186M, are only in Table 2-4.
- **The summary tables** come out cleanly, except that a few rows wrap onto two lines (Walnut in Table 2-3; Imperial Valley in Table 2-5).
- **Spreadsheets:** the July 2026 [Transmission Development Forum "Approved Projects" workbook](https://www.caiso.com/documents/approved-projects-transmission-planning-process-jul-2026.xlsx) lists 235 approved, in-progress upgrades by utility, with finish year and status but no cost. The [capital cost workbook](https://www.caiso.com/documents/2025-2026-transmission-access-charge-high-voltage-capital-cost-estimates.xlsx) gives a total cost for 136 rows, but says it "should not be relied upon for any other purpose". Neither has a substation column; the substation is only in the upgrade name.
- **Inference:** about 1-2 days to parse Appendix H each year and join the forum workbook for status.

### 3.3 How many of our substations match?

Method: I took the 164 canonical names in `src/interconnection_agent/poi/aliases.csv` (all used by waiting projects) and stripped voltage and words like "Substation". A name counts as a match if it appears as a whole word in an upgrade's name, or in its description for Appendix H. For lines ("A-B 230 kV Line"), either end may match. The matches are unreviewed.

| Upgrade list | Our names matching |
|---|---|
| 2025-26 new upgrades, Appendix H (cost + year) | 39 of 164; 38 after removing one false match (Volta-South matched "South Oakland") |
| All approved upgrades in progress (forum workbook) | 91 of 164 |
| Capital cost workbook (cost) | 72 of 164 |

The 38 Appendix H matches cover 62 of 270 waiting projects. 27 are the substation itself, for example Newark 230 kV, Metcalf 230 kV, Midway 115/230/500 kV, Tesla 230/500 kV, Walnut, Etiwanda and Los Esteros. 11 are lines with one end at an upgraded substation. A random sample of 15 forum-workbook matches all named the right substation (hand-checked). But some matches are at a different voltage or part of the substation (e.g. "Midway 500 kV" matched "Midway 115 kV Bus Upgrade" in Appendix H). **Inference:** show these as "planned upgrades at this substation", not "for this connection", and review the alias-to-upgrade links by hand like the existing alias table.

### 3.4 Who pays

- **Upgrades in the plan:** utilities recover them through the transmission access charge. For lines of 200 kV and above, CAISO pools all utilities' costs into one "postage stamp" rate charged to every utility serving customers in its area. Lower-voltage costs are charged to the local utility's customers ([CAISO, How Transmission Cost Recovery Through the TAC Works](https://www.caiso.com/Documents/BackgroundWhitePaper-ReviewTransmissionAccessChargeStructure.pdf), p. 5). In short, all electricity customers pay, not the connecting project.
- **Upgrades a project triggers** (section 2): the project pays up front. Wider-grid upgrade costs are usually refunded with interest over up to 20 years once it runs. The project keeps paying for its own connection equipment (LBNL 2026 report, p. 9; Brattle, p. 35).
- **Suggested label:** *"Planned grid upgrade (paid by all customers, driven mainly by demand growth)."* The plan says more than half its cost is driven by forecast demand growth ([decision slides](https://www.caiso.com/documents/decision-on-iso-2025-2026-transmission-plan-presentation-may-2026.pdf), slides 2 and 4).

### 3.5 May we republish it?

CAISO's [Terms of Use](https://www.caiso.com/privacy-terms-of-use) say most public material "may be used by you provided that you keep intact all copyright, trademark and other proprietary notices and that you credit the California ISO". This is the same basis on which we already use the queue report (`data/README.md`). Quoting short passages and figures with a citation fits these terms. The terms do not mention commercial use (open question). The capital cost workbook's own "do not rely" warning argues for using the plan and Appendix H for costs.

## 4. Area cost to make room: CAISO transmission capability estimates

Every year CAISO gives the CPUC a spreadsheet of grid bottlenecks for full-capacity status ([2026 package](https://www.caiso.com/library/transmission-capability-estimate-inputs-for-cpuc-integrated-resource-plan-jul-15-2026)). [Attachment A](https://www.caiso.com/documents/attachment-a-transmission-capability-estimates-for-use-in-the-cpuc-irp-process-2026.xlsx) gives, for each bottleneck, the MW that fit today, the upgrade that would add more, the MW it adds, and its cost in 2022 dollars. [Attachment B1](https://www.caiso.com/documents/attachment-b1-constraint-mapping-2026-ipe.xlsx) lists 759 substations and the bottlenecks behind them. Both are marked "CAISO PUBLIC". The costs have not been updated since at least 2024 ([white paper](https://www.caiso.com/documents/transmission-capability-estimates-white-paper-2026.pdf), p. 9, footnote 6).

**Measured.** 42 of 65 bottlenecks have both MW and cost. Cost per kW of new room ranges from $9 (Antelope-Vincent) to $2,506 (North of Magunden), median $108. I linked queue rows to bottlenecks by loose substation-name matching (unreviewed) and kept each project's highest figure:

| Queue sheet | Rows | With an area $/kW | Substation names with a $/kW | $/kW min / median / max |
|---|---|---|---|---|
| Waiting | 270 | 171 (63%) | 92 of 143 | 11 / 133 / 2,506 |
| Built | 249 | 171 (69%) | 89 of 141 | 27 / 112 / 2,506 |
| Withdrawn | 1,759 | 1,105 (63%) | 486 of 858 | 11 / 133 / 2,506 |

This is the cost to grow an area, not a quote for one project. At Windhub the area figure is $245/kW, while the EdSan projects there paid $3-27/kW.

## 5. Other public sources

- The [POI heatmap](https://www.caiso.com/poi-heatmap/) shows available MW, not cost: its [FAQ](https://www.caiso.com/documents/points-of-interconnection-heatmap-frequently-asked-questions.pdf) never mentions cost.
- The [Cluster 16 restricted-substation list](https://www.caiso.com/documents/cluster-16-restricted-point-of-interconnection-poi-information.pdf) flags full substations, without dollar amounts.
- The utilities' [per-unit cost guides](https://www.caiso.com/library/current-cost-guides) are generic equipment prices.
- CAISO says the study reports with costs are on the members-only portal ([library](https://www.caiso.com/library/interconnection-facility-information)).
- The Brattle 2024 cost table covers SPP, NYISO, PJM, MISO and ISO-NE only (Table 5).
- I found no open GitHub or Zenodo dataset of CAISO project costs (web search, 2026-10-05).

## Recommendation

1. **"Planned upgrades here" (owner's idea): use the transmission plan.** Parse Appendix H for cost range and finish year, and the forum workbook for status of older upgrades. Link them to substations through a reviewed table. Label them as paid by all customers and driven mainly by demand, never as the project's cost, and credit CAISO. Coverage: 38 of 164 of our substation names for the newest plan, and 91 including older upgrades still being built (unreviewed name matching). **Inference:** 2-3 days of work.
2. **"How costly to connect here": use the capability estimates (section 4)**, worded as "making room for more projects in this area is estimated at about $X per kW". Coverage: about 63% of waiting projects.
3. **Optional:** a few real figures from FERC-filed agreements, each cited by accession number.
4. **Obligations:** credit California ISO and keep its notices. Cite FERC accession numbers. Do not imply endorsement.

## Open questions

- Is it fine to show demand-driven upgrades next to a generator project? Users may read them as that project's cost.
- Do we show the cost range ($31-63M) or the table's single figure ($63M)?
- Do the CAISO terms cover a public, possibly commercial, site? Should we ask CAISO?
- Should upgrade-to-substation links go into the existing reviewed alias process?
- Would CAISO share study costs aggregated by area? That would answer the withdrawal question directly.
