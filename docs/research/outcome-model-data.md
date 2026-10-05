# Research: which data feeds the outcome model

*Research note for issue #38, October 2026. All figures were measured with throwaway scripts
that read the two frozen workbooks in `data/` directly. They are not yet reproduced by tested
code. Sentences marked **Inference** are my own reasoning.*

## Summary

- Every one of the 2,278 projects in CAISO's own file appears in LBNL's CAISO rows under the
  same queue number and queue date. LBNL adds 590 rows, all of them Cluster 15.
- The withdrawn-count gap (LBNL 2,200 vs CAISO 1,759) is explained in full: +482 Cluster 15
  withdrawals that only LBNL lists, −41 withdrawals CAISO recorded in 2026 after LBNL's cut-off.
- Where both sources give an outcome date, the dates are identical. They are also missing in
  the same rows, so LBNL cannot fill CAISO's gaps.
- The source choice moves the all-CAISO **Chance of Reaching Operation** by about 1 point. Adding
  Cluster 15 moves it by about 1.5 points. Missing-date handling moves it by 0.5 points or less.
  All of these are smaller than the sampling noise (roughly ±1.7 points at year 10).
- LBNL's `ia_date` is filled for 83% of operational and 70% of active CAISO projects, but for only
  1.2% of withdrawn ones. A "signed by year 4" estimate built from it (60% by year 10) therefore
  misses most signed-then-withdrew projects, so it reads too high.
- **Recommendation:** use CAISO's own file; keep Cluster 15 out of the old-rules history; keep
  undated outcomes with imputed dates and flag them; do not condition on `ia_date` yet.

## How this was measured

- **CAISO file:** `data/publicqueuereport.xlsx`, tabs "Grid GenerationQueue" (270 active),
  "Completed Generation Projects" (249) and "Withdrawn Generation Projects" (1,759). Headers are on
  row 4. The sheets say "Report Run Date: 07/24/2026", which is used as the snapshot date. A
  *snapshot date* is the day the data was frozen: projects still waiting are only known to be
  waiting up to then.
- **LBNL file:** `data/LBNL_Ix_Queue_Data_File_thru2025.xlsx`, sheet "03. Complete Queue Data",
  headers on row 2, filter `region == "CAISO"`. This gives 2,868 rows: 432 active, 235
  operational, 2,200 withdrawn and 1 suspended. The snapshot is the end of 2025
  ([dataset page](https://emp.lbl.gov/queues); field meanings come from the file's own sheet
  "04. Data Codebook").
- **Matching:** LBNL `q_id` against CAISO "Queue Position", both upper-cased as text.
- **Estimator:** a hand-written Aalen-Johansen estimate, with the clock running in years from
  queue date (CAISO "Queue Date", LBNL `q_date`) to the online or withdrawn date. In plain terms,
  it walks forward through time and asks what share of the projects still in the queue reached
  operation or withdrew; projects still waiting count only for the years we have watched them.
  **"Followed at year N"** is how many projects were still in the queue and watched for at least
  N years; when it is small, the year-N figure rests on very few projects.
- **Technology:** *solar* means any listed component is solar, so solar+storage hybrids count
  (CAISO Fuel-1..3 / Type-1..3, LBNL `type_1..3`). *Battery* means standalone storage: every
  listed component is a battery (CAISO), or `type_clean == "Battery"` (LBNL). On the 2,278
  matched projects the sources agree on solar for all and on battery for 2,271.
- **Uncertainty:** 95% ranges from 400 bootstrap resamples. A *bootstrap* redraws the projects at
  random with replacement and recomputes the estimate, to show how much it would wobble.

## (a) CAISO's own file or LBNL's CAISO rows?

**Record matching.** All 2,278 CAISO queue positions have an LBNL row with the same queue date.
Neither file has duplicate queue numbers. Both keep the same 110 letter-suffixed positions (e.g.
"643AB", phases split off an earlier request) as separate rows. Very old projects (queued
1999–2005) are present in both.

The only rows LBNL has that CAISO lacks are the 590 with `cluster == "Cluster 15"`, all queued
on 17 April 2023. CAISO publishes Cluster 15 in a separate queue report
([CAISO notice](https://www.caiso.com/notices/cluster-15-interconnection-request-queue-report-posted)).

**Status cross-tab of the 2,278 matched projects** (CAISO status → LBNL status):

| | Count | Why they differ |
|---|---|---|
| withdrawn → withdrawn | 1,718 | — |
| withdrawn → active | 41 | CAISO withdrawal dates are all in 2026, after LBNL's cut-off (33 are Cluster 14) |
| operational → operational | 233 | — |
| operational → active | 16 | 12 came online 2025-05-28 to 2026-07-22; 4 have no online date |
| active → active | 267 | — |
| active → operational | 2 | Queue numbers 606 and 356. LBNL gives online dates (2012, 2017); CAISO still lists them active |
| active → suspended | 1 | Queue number 1507 |

**The withdrawn gap, reconciled:** LBNL's 2,200 = 1,718 shared + 482 Cluster 15. CAISO's 1,759 =
1,718 shared + 41 withdrawn in 2026. Of the 482 Cluster 15 withdrawals:

- 420 are dated 2 December 2024. That was the last day of CAISO's Cluster 15 resubmission window
  ([CAISO notice](https://www.caiso.com/notices/cluster-15-application-resubmission-window-opening-10-1-24)),
  so these are the requests that did not resubmit. LBNL says it counts them as withdrawn
  (sheet "02. Data Sample by Region", note 4).
- The other 62 withdrew during 2025.
- 108 Cluster 15 rows remain active in LBNL.

Snapshot dates and Cluster 15 explain the whole gap. Duplicates and old projects do not
contribute.

**What the choice does to the estimate** (Chance of Reaching Operation, year 10 / year 15):

| Data choice | All CAISO | Solar | Battery |
|---|---|---|---|
| A. CAISO file, undated outcomes dropped (baseline) | 12.1% / 15.2% | 12.2% / 15.6% | 13.4% / 20.8%† |
| B. LBNL CAISO rows without Cluster 15 | 13.0% / 15.8% | 12.7% / 16.3% | 16.3% / 16.3%† |
| C. LBNL CAISO rows with Cluster 15 | 11.5% / 14.0% | 11.9% / 15.3% | 11.9% / 11.9%† |
| D. CAISO file + LBNL's Cluster 15 rows | 10.7% / 13.4% | 11.4% / 14.7% | 9.8% / 15.2%† |
| 95% bootstrap range around A | 10.4–13.7 / 13.3–17.0 | 10.2–14.5 / 13.2–18.4 | 8.6–18.9 / 15.5–27.1 |

Counts: A n = 2,224 (235 operational, 1,719 withdrawn, 270 waiting; solar 1,235, battery 475);
B 2,228 (225 / 1,678 / 325); C 2,818; D 2,814. Followed at year 10 / 15: 105 / 32 (CAISO),
91 / 25 (LBNL).

† No standalone battery project has been followed for 15 years: zero are left at year 15, so the
year-15 battery figure is just where the curve stopped. At year 10, only 10–13 battery projects
are still followed.

**Reading the table:**

- B sits about 1 point above A because LBNL is 7 months older. It does not yet see the 41 recent
  withdrawals, so those projects still count as waiting.
- Adding Cluster 15 (C, D) puts about 480 withdrawals at roughly 1.6 years. That lowers every
  later figure, by 3.6 points for battery at year 10 (251 of the 482 were batteries).
- **Inference:** Cluster 15 has no effect on an estimate for a project that has already waited 3+
  years. Every Cluster 15 row leaves the calculation before 2.7 years. Every project in CAISO's
  active tab was queued in 2021 or earlier.
- The technology definition matters too. Using only the first-listed fuel, CAISO battery becomes
  n = 682 and 12.6% / 20.1%. That is probably why the earlier throwaway check got different
  battery figures (10.7% / 17.4%).

## (b) Is LBNL's `ia_date` good enough?

`ia_date` is the date the interconnection agreement (IA) was signed. The IA is the contract that
follows the studies. The table counts LBNL CAISO rows, excluding Cluster 15, with `ia_date` filled:

| Entry years | Operational | Withdrawn | Active |
|---|---|---|---|
| 2000–07 | 42 / 59 | 8 / 224 | 12 / 13 |
| 2008–11 | 79 / 86 | 2 / 567 | 13 / 13 |
| 2012–15 | 39 / 45 | 2 / 269 | 25 / 28 |
| 2016–19 | 32 / 39 | 5 / 325 | 80 / 89 |
| 2020–23 | 4 / 6 | 3 / 333 | 98 / 181 |
| **All** | **196 / 235 (83%)** | **20 / 1,718 (1.2%)** | **228 / 324 (70%)** |

**Active projects:** the gap is genuine. In 2020–23, many have not signed yet. CAISO marks 218 of
its 270 active projects "Executed", and LBNL has a date for 204 of those 218.

**Withdrawn projects:** the gap is mostly missing data, not "never signed".

- CAISO's IA Status column is blank for 1,656 of 1,759 withdrawn projects. It says "Executed" for
  62 and "Terminated" for 9. LBNL dates only 27 of those 71.
- 375 withdrawn projects completed Phase II, the last study before an IA. Only 68 of them show
  Executed or Terminated.
- For comparison, nationally 35% of requests that signed an IA in 2000–2022 had withdrawn by the
  end of 2025 (LBNL file, sheet "27. Post-IA Completion").

**Another quirk:** in 15 LBNL rows `ia_date` comes *after* the online date. For example, queue
number 33 came online in 2006 but has an IA date in 2021. **Inference:** `ia_date` is sometimes
the latest amended agreement, not the first signing.

**Does CAISO give an equivalent?** No. "Interconnection Agreement Status" (Executed / In Progress
/ Filed Unexecuted / Terminated) is the status on the report date, with no date. It cannot say
whether a past project had signed *by the same age*. Using it in a backtest would leak later
information into the past.

**Is an "IA signed by year 4" estimate feasible?** It can be computed, but it is not trustworthy
today. It uses a *landmark* approach: restart the clock at year 4 and use only projects still
waiting then. This is LBNL CAISO rows excluding Cluster 15, chance of operation by year 10 / 15
after entry:

| Group (still waiting at year 4) | n | Operational / withdrawn / waiting | By year 10 | By year 15 |
|---|---|---|---|---|
| All, CAISO file (time only) | 679 | 189 / 220 / 270 | 32.9% | 42.9% |
| All, LBNL | 682 | 178 / 179 / 325 | 35.5% | 44.7% |
| `ia_date` within 4 years of entry | 228 | 99 / **9** / 120 | 60.4% | 64.4% |
| No `ia_date` by year 4 | 454 | 79 / 170 / 205 | 21.9% | 33.1% |
| Signed, plus 25 withdrawn marked Executed/Terminated with no date | 253 | 99 / 34 / 120 | 52.4% | 55.6% |

Only 9 of the 228 "signed" projects (4%) withdrew, against 35% nationally, so 60% is an upper
bound (and its year-15 figure rests on 10 followed projects). Adding just the 25 dateless signed
withdrawals cuts it by 8 points, and more are likely hidden among the 280 Phase II withdrawals
with a blank IA status. Waiting time alone is reliable, and already moves the chance from 12% to
33% at year 10.

## (c) Projects with no outcome date

**Who they are:**

- 39 withdrawn projects with no date. All were queued 2000–2007 under the "Amendment 39" or
  "Pre-Amendment 39" procedures: 28 gas or other, 9 wind, 2 solar. CAISO's earliest recorded
  withdrawal date is 11 January 2006. **Inference:** these left before CAISO began recording
  withdrawal dates.
- 12 operational projects with no date, queued 2006–2021. Every one has a "Proposed On-line Date
  (as filed with IR)", 1.6–4.6 years after entry.

**Can LBNL fill them?** No. LBNL also has no date for the 39 withdrawals. Of the 12, LBNL lists 8
as operational with no date and 4 as still active. Wherever both sources record the same outcome,
the dates match exactly (225 operational, 1,679 withdrawn).

**What the options do** (CAISO file, year 10 / year 15):

| Option | All | Solar | Battery |
|---|---|---|---|
| Drop both groups (baseline A) | 12.1 / 15.2 | 12.2 / 15.6 | 13.4 / 20.8 |
| Keep the 39 withdrawals, dated at entry, at the 2.0-year median wait, or at 1 Jan 2006* | 11.9 / 14.9 | 12.2 / 15.6 | 13.4 / 20.8 |
| Keep the 39, dated at the snapshot date (an implausible ~20-year wait) | 11.5 / 14.0 | 12.1 / 15.5 | 13.4 / 20.8 |
| Keep the 12 operational at their proposed online date (or at entry) | 12.6 / 15.6 | 12.5 / 16.0 | 14.7 / 21.9 |
| Keep the 12 at the snapshot date (latest possible) | 12.3 / 15.5 | 12.2 / 15.6 | 13.8 / 22.6 |
| Keep both (withdrawals at median, operational at proposed date) | 12.4 / 15.3 | 12.5 / 16.0 | 14.7 / 21.9 |

*All three dates give the same result because each falls before year 10. The median wait is
1.96 years, taken from the 185 dated CAISO withdrawals queued 2000–07.

Dropping a project whose outcome is known biases the estimate *away* from that outcome. Dropping
the 39 old withdrawals adds 0.2 points. Dropping the 12 operational projects removes 0.5 points,
or 1.3 points for battery: 7 of the 12 are batteries, and battery has few successes. The exact
imputed date barely matters, provided it is plausible. Every option stays well inside the
bootstrap range.

## (d) Date completeness and oddities

| Field | CAISO file | LBNL CAISO rows |
|---|---|---|
| Queue date | 2,278 / 2,278 | 2,868 / 2,868 |
| Online date (operational) | 237 / 249 (95.2%) | 227 / 235 (96.6%) |
| Withdrawn date (withdrawn) | 1,720 / 1,759 (97.8%) | 2,161 / 2,200 (98.2%); 1,679 / 1,718 (97.7%) without Cluster 15 |
| IA date | none | see (b) |

**Oddities:**

- **Outcome before queue date, same in both files (3 rows):** queue number 98 (online
  2005-12-31, queued 2006-03-09), 1040 (online 2014-01-03, queued 2014-04-30), 643AB (withdrawn
  2010-07-26, queued 2010-07-31). Dropping them or setting their wait to zero moves nothing by
  more than 0.1 points.
- **Two request dates in CAISO's file:** "Interconnection Request Receive Date" differs from
  "Queue Date" by more than a day for 1,093 rows (more than 31 days for 168). LBNL's `q_date`
  equals "Queue Date" in all 2,278 matched rows, so use "Queue Date".
- **LBNL active rows with an online date (23),** e.g. Little Bear Solar 1–4. These look like
  phased projects partly online; `on_date` must not be read as "operational" unless `q_status`
  agrees.
- **LBNL dates past its cut-off:** 2 withdrawal dates fall in January 2026.
- **Long waits:** only 4 CAISO projects came online more than 15 years after entry (15.1–15.8).
- **Batch dates:** 84 withdrawals on 25–26 November 2008 look like a clean-up; 420 Cluster 15
  rows share 2024-12-02.

## Recommendation

1. **Source: CAISO's own file.** It covers every non-Cluster-15 project LBNL has, is 7 months
   newer (41 more withdrawals, 12 more dated operations) and is what the product already ingests.
   Use LBNL's CAISO rows as a cross-check, allowing about 1 point for the snapshot gap.
2. **Cluster 15: keep it out of the old-rules history.** It ran under the post-reform rules and
   has no effect on projects already waiting 3+ years. Report "482 of 590 Cluster 15 requests
   (82%) left within 2.7 years, 420 on the resubmission deadline" as a separate LBNL-sourced fact.
   If an estimate *from entry* is ever shown, state both versions (12.1% vs 10.7% at year 10).
3. **Missing dates: keep and impute, flagged.**
   - Date undated withdrawals at the cohort's median wait-to-withdraw (or 1 January 2006; the
     result is the same).
   - Date undated operations at their proposed online date.
   - Mark both as imputed in the provenance.

   Result: 12.4% / 15.3%. Exclude the 3 outcome-before-entry rows or set their wait to zero; it
   makes no difference.
4. **`ia_date`: do not condition on it yet.** Condition on time already waited instead (32.9% by
   year 10 for a project still waiting at year 4). Show CAISO's IA Status as a plain, sourced fact
   beside the number.
5. **Battery:** do not show a year-15 figure. Show year 10 only with its wide range (about
   9–19%).
6. **Write down the technology definition.** It changes battery figures by several points.

## Open questions

1. Is there a source of IA signing dates for *withdrawn* CAISO projects? Older CAISO queue reports
   or FERC filings of agreements might have them. Without one, an IA-conditioned estimate stays an
   upper bound.
2. Should a Cluster 15 request that did not resubmit count as a withdrawal for "new project"
   estimates, or as a separate exit caused by the rule change?
3. Should solar+storage hybrids count as solar, as battery, or as their own group?
4. How long before CAISO's file is refreshed? Its 7-month lead over LBNL is what moves estimate B
   by about 1 point.
5. Would CAISO's separate Cluster 15 queue report give post-reform outcomes directly? CAISO says
   177 of 255 resubmissions passed scoring
   ([summary](https://www.caiso.com/documents/summary-of-cluster-15-intake-scoring-results.pdf)).
