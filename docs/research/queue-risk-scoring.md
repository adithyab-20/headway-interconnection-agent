# Research: how to score queue risk at a substation

*Research note, October 2026. Sentences marked **Inference** are my own reasoning. Everything
else is attributed to the linked source. "Measured here" figures come from a quick read of
`data/` while writing this note and are not yet reproduced by tested code.*

## Summary

- No source we found publishes a substation-level completion probability. Berkeley Lab (LBNL)
  reports simple cohort shares: of all requests made in 2000–2020, the fraction that is
  operational, withdrawn or still active today. Its timelines are measured only on projects that
  finished.
- Competing-risks survival analysis is the standard tool for "chance of reaching operation within
  N years" when some projects are still waiting. Python has solid ready-made estimators for it.
  For a regression version (Fine-Gray), no mainstream Python library exists.
- The evidence on what predicts completion points to **cost estimates**, **study stage / signed
  agreement**, **region**, **vintage** and **technology**. Whether the substation itself matters
  is untested.
- From Cluster 15 on, CAISO no longer uses the Phase I / Phase II studies. A new project today
  goes through a process that no past project went through.
- **Recommendation:** keep real units. But compute probabilities at ISO × technology level from
  LBNL's CAISO rows. Make substation output descriptive (counts and MW with their sources), not a
  probability. Defer "risk-adjusted MW vs. MW historically connected" until substation mapping of
  completed and withdrawn projects improves. Backtest at ISO level.

## 1. Prior work on modelling queue outcomes

**LBNL "Queued Up", 2026 edition (data through end-2025)**
([PDF](https://emp.lbl.gov/sites/default/files/2026-06/Queued%20Up%202026%20Edition.pdf)).

- *How it computes completion rates:* LBNL takes every request submitted 2000–2020 and reports
  its status at end-2025. Still-active projects stay in the denominator as their own slice. For
  that cohort:

  | | Share of requests | Share of capacity |
  |---|---|---|
  | Operational | 19% | 13% |
  | Withdrawn | 71% | 75% |
  | Still active | 9% | 10% |

  LBNL warns that recent cohorts' final outcome "may not yet be determined" (slide 35). CAISO
  completed 8% of requested capacity, against 24% in ERCOT (slide 37). This is a share at a fixed
  cutoff date, not a survival estimate.
- *Stage matters:* of the capacity that signed an interconnection agreement (IA) in 2000–2022,
  41% had withdrawn by end-2025 and 43% was operational (slide 38). Most 2025 withdrawals
  happened in the system-impact / cluster-study phase. That finding covers only the 47% of
  withdrawn requests whose phase was reported (slide 39).
- *How it measures time to operation:* only for projects that reached operation, grouped by the
  year they came online. The median was 61 months for projects built in 2025 (slides 51, 55).
  CAISO has only 8–19 such projects per year in 2019–2025 (slide 51). Larger projects take longer
  (slide 54). Time to withdrawal is reported separately (slides 41–42).
- *How it handles Cluster 15:* LBNL counts Cluster 15 requests that did not re-submit in 2024
  (as CAISO required) as withdrawn (slides 33, 41). **Measured here:** LBNL has 2,200 withdrawn
  CAISO rows, while CAISO's own withdrawn tab has 1,759. That tab shows only 43 withdrawals dated
  2024. **Inference:** the gap is partly these non-resubmittals, so the two sources' withdrawal
  rates will differ.

**Johnston, Liu & Yang, NBER WP 31946 (Dec 2023, not peer-reviewed)**
([paper](https://www.nber.org/papers/w31946)). The data are 4,085 PJM requests from 2008–2020,
hand-coded from 7,117 study PDFs.
- A study cost estimate above $0.1M/MW is linked to a 12-point higher chance of withdrawing
  before the next study at Study 1, and 23 points at Study 2 (Table 2).
- Withdrawals cluster in the two months after a study arrives.
- Size, state, fuel and year explain only part of the variation in cost (R² 0.41).

**LBNL cost brief, PJM** ([Jan 2023](https://emp.lbl.gov/publications/interconnection-cost-analysis-pjm)).
Withdrawn requests faced a mean cost of $599/kW, against $84/kW for recently completed ones.
Network upgrades account for most of the gap. We found no CAISO equivalent.

**Survival studies.** We found no peer-reviewed competing-risks study of interconnection queues.
- An unreviewed public project
  ([tiwari-nikita/grid-storage-analysis](https://github.com/tiwari-nikita/grid-storage-analysis))
  applies the Aalen-Johansen method to 20,087 LBNL requests. It reports 11.2% built within 5
  years and 20.0% within 10. It finds that treating withdrawal as ordinary censoring overstates
  completion "2.9×". It gives a 2.7% chance for a 200 MW battery in CAISO, against 22.6% in
  ERCOT. Useful as a sanity check only.
- A single-author preprint ([arXiv 2609.10455](https://arxiv.org/abs/2609.10455)) finds that
  withdrawals cluster in time and within technology types.

**What predicts completion (synthesis):**
- Region, vintage and technology (LBNL).
- Study stage and a signed IA (LBNL slide 38).
- Cost estimates (NBER, LBNL cost briefs).

No source tests whether the substation itself predicts completion once cost is accounted for.

## 2. Methods and Python implementations

**Key terms.**
- A *censored* project is one still waiting at the data snapshot: we know it has not finished,
  but not how it will end.
- *Competing risks* means each project ends one of two ways (operation or withdrawal), and one
  rules out the other.
- *Cumulative incidence* is the probability of having reached operation by year N, allowing for
  the chance of withdrawing first.

A standard tutorial says the naive 1 − Kaplan-Meier approach gives "estimates of incidence that
are biased upward" when competing events exist. It recommends subdistribution (Fine-Gray) models
for prediction
([Austin, Lee & Fine, *Circulation* 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4741409/)).

| Library | What it gives | Notes |
|---|---|---|
| lifelines [`AalenJohansenFitter`](https://lifelines.readthedocs.io/en/latest/fitters/univariate/AalenJohansenFitter.html) | Cumulative incidence for one event; 0 = censored | Adds small random jitter to tied times; variance calculation is slow |
| scikit-survival [`cumulative_incidence_competing_risks`](https://scikit-survival.readthedocs.io/en/stable/api/generated/sksurv.nonparametric.cumulative_incidence_competing_risks.html) | Cumulative incidence for all causes, with confidence intervals | `time_min` gives estimates *conditional on having already waited* a given time |
| statsmodels [`CumIncidenceRight`](https://www.statsmodels.org/stable/generated/statsmodels.duration.survfunc.CumIncidenceRight.html) | Cumulative incidence per cause, with standard errors | — |
| R [`cmprsk`](https://cran.r-project.org/web/packages/cmprsk/cmprsk.pdf) | Fine-Gray regression (`crr`) | We found no widely used Python equivalent |

**Partial pooling / shrinkage.** *Shrinkage* pulls an estimate based on a few projects toward a
larger group's average, and pulls harder the fewer projects there are. The classic treatment is
empirical Bayes ([Efron & Morris 1975](https://doi.org/10.1080/01621459.1975.10479864)). PyMC
documents a hierarchical beta-binomial version
([example](https://www.pymc.io/projects/examples/en/latest/generalized_linear_models/GLM-hierarchical-binomial-model.html)).

**Inference on how shrinkage would play out here:**
- The simple form is `(k·p_parent + successes) / (k + resolved)`, where `k` is how much weight
  the parent group gets, counted in projects.
- With k ≈ 10–30, a substation with 5 resolved projects keeps only about 15–33% of its own
  signal.
- This works only for projects followed long enough to have finished. Combining shrinkage with
  censoring needs a survival model with a substation-level random effect.

**Backtesting and calibration.**
- *Calibration* means that when the model says 20%, about 20% of those projects actually reach
  operation.
- The *Brier score* is the average squared gap between predicted probability and outcome (0 =
  perfect). The survival version is computed at a chosen horizon and reweights observations to
  account for censoring
  ([scikit-survival `brier_score`](https://scikit-survival.readthedocs.io/en/stable/api/generated/sksurv.metrics.brier_score.html)).
  That implementation handles a single event type only.
- For competing risks, [van Geloven et al., *BMJ* 2022](https://doi.org/10.1136/bmj-2021-069249)
  describe calibration and Brier-score checks using weighting or pseudo-observations.

## 3. CAISO process facts that affect the model

**Phase I / Phase II (GIDAP, Clusters 5–14)**
([Appendix DD](https://www.caiso.com/documents/appendix-dd-generator-interconnection-deliverability-allocation-procedures-as-of-jun-25-2025.pdf)):
- Phase I identifies the needed upgrades. It sets each request's "Current Cost Responsibility,
  Maximum Cost Responsibility, and Maximum Cost Exposure" (§6.2).
- CAISO aims to issue Phase I within 170 days of the annual start (§6.6).
- Phase II starts by about May 1 and is reported within 205 days (§8.5).
- Network-upgrade cost exposure is capped at the lower of the Phase I and Phase II estimates. The
  first financial-security posting is based on Phase I costs (§7.2).
- Transmission Plan (TP) deliverability is allocated after the studies (§8.9).
- If a project's online date is more than 7 years after its request, it must meet "commercial
  viability criteria" to keep its deliverability (§6.7.4).

**Inference:** the first cost signal arrives about a year after entry. Given the NBER result,
withdrawal risk should spike at that point.

**Full Capacity vs Energy Only**
([Appendix A](https://www.caiso.com/documents/appendix-a-master-definition-supplement-as-of-nov-19-2025.pdf)):
- An Energy Only project pays only for reliability upgrades. It gets zero qualifying capacity, so
  it "cannot be considered to be a Resource Adequacy Resource". In plain terms, it cannot sell
  capacity to meet utilities' reliability obligations.
- A Full Capacity project can count up to its qualifying capacity.
- CAISO told FERC that every request in Clusters 10–15 sought TP deliverability
  ([188 FERC ¶ 61,225](https://www.caiso.com/documents/sep-30-2024-ferc-order-accepting-tariff-amendment-interconnection-process-enhancements-2023-er24-2671.pdf), p. 4).
- **Measured here:** the active tab lists 167 Full Capacity, 52 Partial and 51 Energy Only
  projects.

**Inference:** deliverability *requested* barely varies between recent projects. Deliverability
*allocated* (the TPD columns) is the more useful field.

**2023+ reforms** ([188 FERC ¶ 61,225](https://www.caiso.com/documents/sep-30-2024-ferc-order-accepting-tariff-amendment-interconnection-process-enhancements-2023-er24-2671.pdf); [189 FERC ¶ 61,195](https://www.caiso.com/documents/dec-16-2024-ferc-order-accepting-queue-management-interconnection-process-enhancements-2023-track-2-tariff-amendment-er25-131.pdf); LBNL slides 10, 69):
- **Timing:** Cluster 15 was submitted in April 2023, paused in August 2023 and restarted under
  new rules on October 1, 2024. Cluster 16 opens in October 2026.
- **New procedure:** Cluster 15 onward falls under the Resource Interconnection Standards
  (Appendix KK), not GIDAP. Its steps are a cluster study, a restudy and a facilities study; there
  is no Phase I / Phase II.
- **Entry screen:** projects seeking deliverability in "Deliverable Zones" are scored on
  viability, system need and commercial interest. Only enough projects to fill 150% of available
  capacity at each constraint go on to be studied.
- **FERC Order No. 2023** (as summarised by LBNL slide 69): first-ready, first-served cluster
  studies; higher at-risk deposits; escalating withdrawal penalties; 90% site control at request
  and 100% by the facilities study; penalties for late studies.
- LBNL calls it "too early to measure" the effect (slide 55). FERC's own fact sheet could not be
  fetched for this note.

**Inference:** pre-2023 outcomes describe the old rules. Present them as history, not as a
forecast for new requests.

## 4. Existing tools that score queue risk

| Tool | What public pages say | Status |
|---|---|---|
| **Enverus** | "Project Completion Probability" shown as a percentage. It comes from a "binary classification machine learning model" trained on past operational and withdrawn projects. Inputs include status, capacity, developer, days in queue, substation capacity and study duration. Claims "70-80% accuracy" ([2024](https://www.enverus.com/blog/successfully-navigating-the-interconnection-queue-with-project-probability/), [2025](https://www.enverus.com/blog/predict-iso-project-success-with-interconnection-queue-probability/)) | Confirmed (vendor blog) |
| **Interconnection.fyi** | Status, MW, type, county, year; no score ([homepage](https://www.interconnection.fyi/)) | Confirmed |
| **GridStatus** | Queue browser and API with standardised columns, per search snippets. Pages blocked our fetch | Unconfirmed |
| **LevelTen** | Search snippets mention assessing "likelihood of completion"; not visible on the pages we fetched | Unconfirmed |
| **Grid Strategies / Brattle** | Letter grades for *ISOs*, not projects; CAISO got "B" ([2024](https://gridstrategiesllc.com/wp-content/uploads/2024/03/AEI-2024-Generation-Interconnection-Scorecard.pdf)) | Confirmed |

**Inference on Enverus's accuracy claim:** in CAISO raw data, about 88% of resolved projects
withdrew (1,759 of 2,008). A model that always says "withdraws" therefore scores about 88%
"accuracy". An accuracy figure without a baseline says little. Report calibration instead.

## 5. Recommendation for our scoring approach

**Adopt**

1. **Real units, not points:**
   - the chance of reaching operation within N years, with an interval;
   - the median time to operation and to withdrawal;
   - MW waiting at the substation.

   No source justifies the weights a points score would need.
2. **Aalen-Johansen cumulative incidence** (lifelines or scikit-survival).
   - Outcomes are operation vs. withdrawal. Still-active projects are censored at the snapshot
     date.
   - **Measured here:** the dates are well populated. CAISO raw has Withdrawn Date for 98% of
     withdrawn projects and Actual On-line Date for 94% of completed ones. LBNL's CAISO rows have
     98% and 97%.
   - This replaces ADR 0002's per-vintage rate as the headline. Keep the vintage table as a
     cross-check.
3. **Estimate at ISO × technology level**, optionally adding a coarse size band and a pre/post-2020
   era. Use LBNL's CAISO rows. These groups have hundreds of projects; substations do not.
4. **Condition on how far a project has already got** when discounting MW already in the queue
   (use `time_min`).
   - **Measured here:** 266 of 270 active projects have Phase I complete and 218 have an executed
     IA. Every one is Cluster 14 or earlier (queue dates up to 2021).
   - LBNL's post-IA figures (43% operational / 41% withdrawn) are a national reference, and
     should be labelled that way.
5. **Backtest at ISO level.**
   - For cutoffs such as 2012, 2014 and 2016, rebuild who was active from dates only.
   - Predict N-year outcomes, then report the Brier score and a predicted-vs-observed table.
   - Do not use study phase, MW or substation as inputs: they are recorded as of the snapshot, so
     using them would leak future information into the past.

**Drop or defer**

- **Substation-level probabilities and shrinkage.**
  - Only 15 substations have ≥5 resolved projects, and 7 have ≥3 operational.
  - Shrunken estimates for those would be roughly 65–85% parent value. That is complexity that
    only looks precise.
  - Show substation history as plain counts beside the ISO-level probability.
- **"Risk-adjusted MW ahead vs. MW historically connected."**
  - Only 73 of 249 operational and 236 of 1,759 withdrawn projects have a mapped substation, so
    the ratio would mostly measure mapping coverage.
  - Show risk-adjusted MW ahead on its own until the mapping improves.
- **Fine-Gray regression:** there is no mainstream Python implementation and the sample is too
  thin.
- **Study phase as a predictor:** the data only shows it as of the snapshot, and the phases don't
  exist for Cluster 15+.
- **Reason for Withdrawal:** 59% blank and 35% "IC Request".

**What the data can and cannot support**

- *Can:* ISO and ISO × technology probabilities and time-to-outcome curves under the old rules,
  with honest intervals. Descriptive substation context.
- *Cannot:*
  - a defensible substation-specific probability;
  - any forecast for post-reform (Cluster 15+) projects;
  - saturation ratios;
  - cost-based risk, because neither dataset holds study cost estimates, even though cost is the
    best-documented predictor.

**Open questions**

1. Which source should supply withdrawal history: CAISO raw (without Cluster 15
   non-resubmittals) or LBNL (with them)? Cross-validation tolerances must allow for the gap.
2. Should a user's project be treated as a new Cluster 16 request (answer: "historical analogue
   only") or as a project already past its studies?
3. Is hand-mapping the remaining ~176 operational substations worth it? It is the prerequisite
   for any saturation metric.
4. Can CAISO study cost data be obtained? Cost is the strongest predictor we lack.
5. Which horizons N to show? Long horizons rest only on old vintages.
