# Experiment Audit Report

**Date:** 2026-10-22  
**Auditor:** GPT-5.6-Sol ultra (fresh same-family reviewer; read-only implementation review)  
**Project:** Worlds 2026 BP Predictor  
**Final run:** `20261022T093531Z-f5eb82ee9db3`  
**Code freeze:** `acbbf9f48bce322ca768686875c7ac676861a86a`  
**Review independence:** `same-family`  
**Acceptance status:** `provisional`

## Overall Verdict: WARN

## Integrity Status: warn

No fake ground truth, self-normalized score, phantom main result, test-selected deployment, or current-game outcome leakage was found. Dataset labels trace to downloaded third-party match records, all reported main and supplemental metrics reconcile from prediction rows, and the selected artifact reproduces those probabilities.

The warning is about what the evidence can support. The selected model has one chronological split and one seed; only 22 held-out records match the actual `WLDs` + source `16.20` / public `26.20` target intersection, with descriptive accuracy `0.54545`, AUC `0.58974`, log loss `0.72044`, Brier `0.26183`, and ECE `0.32262` (`reports/metrics.json:37298-37342`, `reports/RESULTS.md:23-27`). This does not support a reliable Worlds-specific accuracy or calibration claim. Player identities are name-derived and unverified, and the current snapshot cannot reconstruct historical vendor publication state (`data/processed/quality_report.json:200-209`).

## Checks

### A. Ground Truth Provenance: PASS

- The evaluation target is the source team `result`, parsed as binary and checked for complementary opponents before `blue_win` is emitted (`src/worlds_predictor/data.py:28-31`, `src/worlds_predictor/data.py:203-214`, `src/worlds_predictor/data.py:287-304`). No prediction or model output is used as a label.
- The six original player/team CSVs are recorded with URL, row count, byte count, date range, and SHA-256 (`data/raw/sources.json:3-23`, `data/raw/sources.json:25-109`). I independently streamed all six current URLs and obtained the same byte counts and hashes as the local files. The provider page currently lists the same rows and CC BY 4.0 terms: [ChainCC Open Dataset](https://chaincc.lol/free/data/).
- Independent full-table reconciliation found all 28,738 accepted canonical games in the raw team and player files, exactly two accepted team rows and ten accepted player rows per game, zero champion-slot mismatches, and all 28,738 canonical `blue_win` values equal to the raw blue-side `result`. The generated quality report records 30,005 raw games, 28,738 accepted, 1,267 quarantined, and the actual cutoff (`data/processed/quality_report.json:3-25`).
- The source is a third-party observational dataset, not an official immutable truth archive. That limit is disclosed: downloaded records are real dataset observations, while source timestamp semantics, historical publication time, later corrections, and player person identity cannot be proven from the snapshot (`SOURCE_DATA.md:3-12`, `SOURCE_DATA.md:41-55`).
- No official benchmark evaluation script applies to this custom prediction task.

### B. Score Normalization: PASS

- Accuracy, ROC-AUC, log loss, Brier score, ten-bin ECE, and observed win rate are computed directly from binary labels and probabilities; invalid probabilities are rejected (`src/worlds_predictor/evaluation.py:9-31`). No metric is divided by a prediction maximum, minimum, mean, or other model-output statistic.
- Raw probabilities and separately calibrated probabilities are both evaluated and retained (`src/worlds_predictor/model.py:127-145`). The `weights / weights.mean()` operation is training sample-weight scaling, not score normalization (`src/worlds_predictor/model.py:121-126`).
- Independent recomputation from all seven `reports/predictions_*.csv` files matched every raw and calibrated accuracy, AUC, log loss, Brier, and ECE value with maximum absolute error `1.11e-16`. The two reported B-vs-C log-loss deltas matched independently within `6.57e-17` (`reports/metrics.json:38190-38212`).

### C. Result Existence and Numeric Consistency: PASS

- The final metrics file is complete, identifies `real_gt`, records the frozen source hashes and data hash, and contains 15,717 train, 2,968 validation, 716 calibration, and 9,309 test games (`reports/metrics.json:2-65`). The readable report agrees with the JSON, including the selected model and target slice (`reports/RESULTS.md:3-27`).
- The run suffix `f5eb82ee9db3` independently recomputes from the stored config, complete source-hash map, and canonical data hash. Every recorded source hash equals the frozen source tree; the canonical Parquet hash equals `d99ab5...70ce`; the selected artifact hash equals `96803e...369d`.
- The selected `C_catboost_uniform` artifact reproduces all 9,309 raw and calibrated test probabilities with maximum absolute error `1.11e-16`. The selected target-event intersection independently recomputes to the 22 rows and scores recorded at `reports/metrics.json:37298-37342`.
- All seven per-run model artifact hashes, latest metadata/artifact copies, result files, split membership, API/replay outputs, sensitivity outputs, and plot input are aligned to the final run. All 26 entries in the final artifact manifest independently match their recorded hashes and byte sizes (`reports/artifact_manifest.json:2-4`, `reports/artifact_manifest.json:5-109`).
- `reports/split_membership.csv` contains 28,710 unique IDs with counts exactly matching the four reported splits. Labels, dates, and availability timestamps match the canonical table. The 28 unassigned boundary games are deliberately purged because their outcomes are not available at the relevant split cutoff (`src/worlds_predictor/evaluation.py:34-54`, `PROGRESS.md:10-12`).
- The supplemental raw LCK comparison independently reconciles on 502 identical test games, including both metrics and its paired delta. The calibrated supplemental run is honestly `blocked` and contains no model or comparison metrics because its calibration cohort has zero LCK games (`reports/cross_league_sensitivity.md:3-23`, `reports/cross_league_raw_sensitivity.md:3-25`).
- The final automated suite records 174 passing tests and one upstream deprecation warning (`reports/pytest.log:1-10`).

### D. Dead Metric Code: PASS

- `metrics` is called for validation, calibration, test, patch, league, month, seen/unseen league, and exact target-event cohorts (`src/worlds_predictor/model.py:133-154`).
- `paired_day_bootstrap` is called for both logistic and CatBoost B-vs-C comparisons (`src/worlds_predictor/model.py:171-178`), and its output is present in the result file (`reports/metrics.json:38190-38212`).
- Supplemental metric and alignment code is exercised by the completed raw comparison (`src/worlds_predictor/sensitivity.py:124-139`) and guarded by an explicit blocker in the calibrated path. The blocked path does not emit phantom scores.
- Metric edge cases and direct hand calculations are tested (`tests/test_evaluation.py:24-45`, `tests/test_evaluation.py:100-113`); supplemental game/label alignment failures are tested (`tests/test_sensitivity.py:27-49`).

### E. Scope, Leakage, Selection, Identity, and API: WARN

#### Temporal integrity: PASS

- Canonical history loads require both `date < as_of` and `available_at < as_of` (`src/worlds_predictor/data.py:386-405`). Feature creation updates state only when a prior result has `available_at < current_game_date`, and inference also removes the target `game_id` (`src/worlds_predictor/features.py:256-293`).
- Same-timestamp games are atomic; the conservative next-UTC-midnight availability policy prevents same-day result reuse (`src/worlds_predictor/data.py:294-304`, `tests/test_features.py:77-104`). Independent split inspection found no duplicated game ID and no date/timestamp crossing split membership.
- Estimators fit only the train block. Model selection uses raw validation log loss. A separate later calibration block fits the sigmoid calibrator, and test metrics do not select the model (`src/worlds_predictor/model.py:121-145`, `src/worlds_predictor/model.py:171-183`). Calibration-block calibrated scores are in-sample and are not presented as independent evidence (`README.md:101-112`).
- Request timestamps must be timezone-aware with `as_of <= scheduled_start`; inference also requires `as_of` later than the model label cutoff (`src/worlds_predictor/schemas.py:54-79`, `src/worlds_predictor/model.py:256-284`).

#### API and invalid-artifact behavior: PASS

- `/health` now validates the artifact SHA-256, feature-code SHA-256, and timezone-bounded metadata before declaring the model available (`src/worlds_predictor/api.py:20-43`). Independent tests found a tampered artifact produced `available=false`, and `POST /predict` returned HTTP 503 with no probability key.
- The real production paths returned HTTP 200 for both public `Worlds/26.20` and source `WLDs/16.20`; both normalized to model context `WLDs/16.20` and produced the same probability. `WLDs/16.19` returned HTTP 422 (`src/worlds_predictor/context.py:21-47`, `src/worlds_predictor/context.py:57-81`, `reports/api_context_smoke.json:2-14`). Official/configured mismatch is HTTP 503 for every recognized alias (`src/worlds_predictor/api.py:102-120`, `tests/test_api.py:83-104`).
- The public/source patch equivalence is explicitly classified as an inference rather than an official crosswalk. Riot identifies public patch 26.20 as the Worlds patch, while the Riot developer documentation exposes Data Dragon `16.20.1`; the report also records the source `WLDs/16.20` observations ([Riot patch notes](https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-20-notes/), [Riot Developer Portal](https://developer.riotgames.com/docs/lol), `reports/patch_namespace_mapping.json:15-63`).

#### Remaining scope and provenance limits: WARN

- The broad 9,309-game test covers many leagues and tiers. It is not a Worlds-only test (`SOURCE_DATA.md:14-20`, `README.md:108-125`). The actual target intersection has only 22 games and cannot establish reliable event-specific discrimination or calibration (`reports/RESULTS.md:23-27`).
- There is one training seed and one chronological holdout. The CatBoost C-minus-B interval crosses zero, while logistic C is worse than B; this does not establish that BP features improve prediction, much less that BP causes wins (`reports/RESULTS.md:19-21`, `reports/RESULTS.md:29-36`).
- The LCK raw sensitivity is exploratory, uses one league and shared globally computed historical features, and its paired interval crosses zero. The calibrated version is blocked for lack of an LCK calibration cohort (`reports/cross_league_raw_sensitivity.md:25-33`, `reports/cross_league_sensitivity.md:20-30`).
- All 287,380 accepted player rows use `source_playername_unverified`; exact-name continuity can split renames or conflate different people (`data/processed/quality_report.json:200-205`). B/C identity-dependent claims must retain this limitation.
- `available_at` is a conservative retrospective approximation. The current download cannot prove what a vendor published at each historical prediction time or reconstruct later corrections (`data/processed/quality_report.json:207-209`, `SOURCE_DATA.md:53-55`).
- The 26.20-to-16.20 namespace equivalence is evidence-backed and explicitly bounded, but remains an inferred cross-namespace mapping rather than a directly published official crosswalk (`configs/worlds2026.json:13-20`, `reports/patch_namespace_mapping.json:41-63`).

### F. Evaluation Type Classification: PASS

| Artifact/evaluation | Classification | Evidence |
|---|---|---|
| Main chronological model evaluation | `real_gt` | Dataset-provided match outcomes; `reports/metrics.json:20`; raw-to-canonical reconciliation passed. |
| Exact Worlds 2026 target slice | `real_gt` | Same held-out dataset outcomes, filtered to `WLDs` + `16.20`; `src/worlds_predictor/model.py:146-154`. |
| Raw LCK pooled-vs-local sensitivity | `real_gt` | Identical real held-out LCK game IDs and labels; `reports/cross_league_raw_sensitivity.md:3-25`. |
| Calibrated LCK sensitivity | `real_gt` protocol, **blocked/no result** | Zero calibration games; no fabricated metric or artifact; `reports/cross_league_sensitivity.md:13-23`. |
| Historical replay | `real_gt` demonstration, not an evaluation claim | Actual outcome stays only in provenance and is not sent to prediction; `examples/real_match_replay.provenance.json:2-7`. |
| Unit-test fixtures | Synthetic structural fixtures, not `synthetic_proxy` evaluation | Tests explicitly isolate fixtures from product training/results; `tests/test_data.py:1-5`, `tests/test_model.py:1-5`. |

## Resolved Findings During Review

1. **Worlds alias bypass and patch namespace mismatch — resolved.** The original route recognized only long-form Worlds names, allowing actual source league `WLDs` and patch `16.20` to bypass a configured public `26.20` check. The final code recognizes reviewed aliases, normalizes public/source context before feature creation, rejects wrong source versions, exposes input/model context, and records the mapping as an inference (`src/worlds_predictor/context.py:21-81`, `src/worlds_predictor/model.py:239-242`, `reports/replay_prediction.json:83-103`).
2. **False-positive health readiness for a damaged artifact — resolved.** Health now hashes the artifact and feature implementation before reporting availability (`src/worlds_predictor/api.py:20-43`, `tests/test_readiness.py:29-66`).
3. **Ambiguous “sensitivity-only” deployment role — resolved.** The uniform C model is now consistently described as a predeclared selection candidate that also supplies a recency sensitivity arm (`src/worlds_predictor/model.py:111-114`, `src/worlds_predictor/model.py:171-183`, `README.md:112-125`).
4. **Missing target event+patch scope — resolved.** The final evaluator reports the exact 22-game intersection and explicitly rejects a reliable Worlds-specific claim (`src/worlds_predictor/model.py:146-154`, `reports/RESULTS.md:23-27`).
5. **Stale tracker and cross-run artifacts — resolved.** Progress, replay, API smoke, sensitivity, plots, model metadata, result files, and artifact manifest all identify final run `20261022T093531Z-f5eb82ee9db3` (`PROGRESS.md:10-20`, `reports/artifact_manifest.json:2-4`).
6. **Source changed after an intermediate hash capture — resolved.** The final training run was executed after source freeze; its complete source-hash map matches the current tree and its fingerprint recomputes exactly.

## Claim Impact

| Claim | Impact |
|---|---|
| The system trained and evaluated on downloaded professional match outcomes, not model-generated labels | **Supported** |
| Reported broad-test metrics and selected artifact are genuine and reproducible from the saved prediction rows | **Supported** |
| Selection used validation rather than test outcomes | **Supported** |
| Current-game or same-game outcomes do not enter the prediction feature vector | **Supported** |
| The current model has demonstrated reliable Worlds 2026 accuracy or calibration | **Unsupported** |
| C/BP features provide a stable predictive improvement | **Unsupported by this run** |
| C/BP features causally improve winning | **Unsupported** |
| Cross-league transport is established | **Unsupported; exploratory raw sensitivity only** |
| Player identity history is globally verified | **Unsupported** |

## Action Items

1. Keep every public result qualified as an all-league retrospective chronological holdout. Do not promote the 22-game target slice into a Worlds accuracy or calibration claim.
2. Add more completed target-patch Worlds games, repeated seeds, and additional predeclared chronological folds before making event-specific reliability claims. Use a target-relevant calibration design if event calibration is a goal.
3. Treat B-vs-C as descriptive until repeated holdouts show a stable improvement; retain the confounding and non-causal language.
4. Replace name-derived player identities with provider IDs or evidence-backed dated alias mappings, then rebuild data and retrain.
5. Preserve versioned source snapshots and publication evidence if true point-in-time vendor-state claims are required.
6. Reverify the explicit 26.20↔16.20 mapping whenever the provider, official patch, or Data Dragon namespace changes; never generalize it arithmetically.

## Deterministic Verification Summary

- Main prediction rows checked: `7 models × 9,309 rows`; all raw/calibrated metrics reconciled.
- Canonical labels checked against original rows: `28,738 / 28,738` matched.
- Main split IDs: `28,710` unique; `0` overlaps or duplicate IDs; `28` explicitly purged boundary games.
- Final artifact-manifest entries checked: `26 / 26` hashes and byte sizes matched.
- Selected artifact predictions checked: maximum absolute probability difference `1.11e-16`.
- Supplemental raw sensitivity checked: `502` target-league test rows; maximum metric difference `4.17e-17`.
- Real API context checks: public/source aliases equal; wrong patch `422`; tampered artifact health unavailable and prediction `503` without probabilities.
- Test suite: `174 passed`, one upstream deprecation warning.

This is a same-family semantic review. The deterministic evidence checks are reproducible; the overall acceptance remains provisional under the audit skill's reviewer-independence policy.
