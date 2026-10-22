# Claims From the Aggressive Experiment

**Verdict:** `claim_supported: partial`  
**Confidence:** high for the audited snapshot  
**Integrity:** `WARN` because the evidence is retrospective, one-seed, one-split, and event-limited; no integrity fabrication was found  
**Review status:** same-family, provisional

## What the results support

| Claim | Verdict | Evidence |
|---|---|---|
| Enhanced training was actually attempted and completed | **yes** | Three CatBoost candidates were fitted on 15,717 real training games, saved as distinct artifacts, evaluated on fixed temporal segments, and replayed from the saved artifacts (`reports/aggressive/experiment_training.log:1-8`). |
| The product implements an explicit winner with evidence and a support index | **yes** | The winner comes from the calibrated model direction; the index is the validation ECDF rank of distance from the calibrated 0.5 boundary (`src/worlds_predictor/judgment_policy.py:64-108`). Reasons and risks use signed full SHAP groups or explicit evidence gaps (`src/worlds_predictor/judgment.py:157-194`). |
| The support index is a probability | **no** | Code, policy, API output, and UI all label it as a non-probability index (`src/worlds_predictor/judgment_policy.py:101-108`, `frontend/src/components/JudgmentPanel.tsx:32-36`). |
| Strong-group hit rates can be reported descriptively | **yes, qualified** | Selected: 2,072/2,697 = 76.83%; frozen: 2,080/2,666 = 78.02%. These are retrospective, model-specific ECDF cohorts, not a current-match probability or a paired improvement test (`reports/aggressive/judgment_evaluation.json:211-217`, `reports/aggressive/judgment_evaluation.json:418-424`). |

## What the results do not support

### Overall ranking or performance improvement: no

On the same 9,309 reused 2026 test games, the validation-selected `enhanced_recent90_d4` is worse than the frozen standard model:

| Metric | Frozen standard | Selected enhanced | Enhanced − frozen |
|---|---:|---:|---:|
| Accuracy | 0.639489 | 0.636373 | -0.003115 |
| ROC-AUC | 0.697653 | 0.692046 | -0.005607 |
| Log loss | 0.630171 | 0.633306 | +0.003135 (worse) |
| Brier | 0.220150 | 0.221484 | +0.001333 (worse) |

The selected model did improve raw validation AUC, which is why the predeclared validation rule selected it, but that does not establish test generalization. The report says this directly (`reports/aggressive/experiment_results.md:13-18`). Another candidate had better retrospective test scores, but it was not selected and cannot be substituted after viewing the test.

### Strong-call improvement: no

The enhanced strong subgroup has a lower descriptive hit rate than the frozen strong subgroup, and the two subgroups contain different games because each policy ranks its own margins. No common-cohort paired strong-call analysis establishes improvement. The supported statement is only: “Within this reused test set, the enhanced policy's strong group hit 2,072 of 2,697 maps.”

### Worlds-specific reliability: no

The target cohort contains 22 maps and 15 hits. Its unadjusted Wilson interval is approximately 47.3%–83.6%, and it does not adjust for series/day dependence (`reports/aggressive/judgment_evaluation.json:598-634`). This supports a descriptive count, not an event-specific reliability or calibration claim.

### Tactical causal ratings: no

The standardized data does not validate engage, crowd control, early/mid/late power curves, or team-style causal matchup ratings. The implementation correctly withholds them (`reports/aggressive/experiment_protocol.json:46-50`). Champion/roster/pair features are historical outcome associations.

## Suggested claim wording

> We trained and deployed a validation-selected experimental judgment model that produces an explicit winner, a non-probability support index, and evidence summaries from real pre-cutoff history and full-model SHAP contributions. On the previously inspected 2026 holdout, it did not improve overall metrics or strong-call hit rate over the frozen standard model. Strong-group and 22-map Worlds results are descriptive only.

## Missing evidence

1. A preregistered, never-inspected post-cutoff evaluation period.
2. Multiple training seeds and multiple temporal splits.
3. A paired common-cohort analysis for selective/strong calls, including coverage-risk curves and day/series clustering.
4. A materially larger Worlds sample for event-specific accuracy and calibration.
5. Better historical publication-time provenance and verified player identity linkage if those become claim-critical.

## Routing action

`supplement`: keep the current bounded implementation claim, do not claim performance improvement, and revisit result-to-claim only after fresh post-cutoff evidence is available.
