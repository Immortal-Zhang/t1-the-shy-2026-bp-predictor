# Aggressive Experiment Integrity Audit

**Date:** 2026-10-22  
**Auditor:** Fresh Codex reviewer, same-family and provisional  
**Snapshot:** `reports/aggressive/AUDITED_SNAPSHOT.json` (`sha256:21f367f90657de3cfb19bd5900875449955639eb912c34e4d2b98e235cac00cc`)  
**Evaluation type:** `real_gt`

## Overall Verdict: WARN

## Integrity Status: warn

The saved experiment is genuine and internally reproducible. I found no model-generated ground truth, self-normalized performance metric, phantom result, dead evaluation path, post-`as_of` feature leakage, or invented tactical rating in the audited snapshot. The warning is about claim scope: this is one seed and one temporal split, the 2026 test period was already inspected, and the Worlds target cohort contains only 22 maps. Those limits are disclosed in the product and reports.

The validation-selected enhanced model does **not** establish an overall or strong-call improvement over the frozen standard model. It is valid to claim that enhanced training completed and that an explicit winner/evidence/support-index layer was implemented. The combined result-to-claim verdict is therefore `partial`.

## Independent recomputation

- `data/processed/games.parquet` contains 28,738 unique games and binary real outcomes: 13,409 red wins and 15,329 blue wins. Its SHA-256 matches both experiment metadata and enhanced-model metadata.
- All 15 `reports/aggressive/*predictions*.csv` files exist. For all 12 model/segment CSVs, row counts, game IDs, labels, dates, and availability times match the canonical parquet data. Validation, calibration, and test IDs are disjoint, and all four models use identical ordered IDs and labels per segment.
- Independently recomputed accuracy, ROC-AUC, log loss, and Brier score match `experiment_metrics.json` to at most `1.11e-16`.
- Replaying both saved joblib artifacts against `experiment_features.parquet` reproduces raw scores, raw probabilities, and calibrated probabilities to at most `1.11e-16`.
- Judgment CSV recomputation matches exactly: selected 5,924/9,309 (`0.6363734021`), selected strong 2,072/2,697 (`0.7682610308`), frozen 5,953/9,309 (`0.6394886669`), frozen strong 2,080/2,666 (`0.7801950488`), and Worlds 15/22 (`0.6818181818`). Every support-index pair sums to 100 exactly.
- The frozen standard CSV exactly matches the earlier saved 9,309 probabilities (`max_abs_delta=0`). The trained artifacts, policy, evaluation, prediction CSVs, runtime sources, frontend, and executed logs are bound by the 138-file audited snapshot.
- I independently ran the Python suite: 263 passed with one dependency deprecation warning. The bound delivery logs record 55 final targeted Python tests, 61 Vitest tests, a strict production build, and 16 Chromium/WebKit browser tests passing. A second reviewer-side npm invocation was blocked by a local macOS native-binding code-signature mismatch; I therefore treat the bound successful frontend logs as execution evidence and the source/tests as the semantic evidence.

## Checks

### A. Ground-truth provenance: PASS

The target is the source dataset's complementary team result, not a model output. Ingestion joins player and team rows on the composite `(game_id, side)` key and verifies their fields (`src/worlds_predictor/data.py:254-264`), rejects non-complementary opponent results, and writes `blue_win` from the blue team's source result (`src/worlds_predictor/data.py:288-304`). The source manifest identifies ChainCC files, URLs, hashes, row counts, and license (`reports/data_sources.json:2-23`). The quality report records 30,005 source games, 28,738 accepted games, 1,267 quarantined games, and the outcome-availability policy (`reports/data_quality.json:3-25`, `reports/data_quality.json:197-209`). Prediction CSV labels match the parquet labels exactly.

### B. Score normalization: PASS

Performance metrics consume the real binary labels and probabilities directly; accuracy uses `p >= 0.5`, and ROC-AUC, log loss, Brier score, and ECE are computed without division by a model-output maximum (`src/worlds_predictor/evaluation.py:9-31`). The support index does use a validation-margin ECDF, but the code returns `is_probability: false` (`src/worlds_predictor/judgment_policy.py:83-108`), the policy defines it as a rank rather than a win rate (`src/worlds_predictor/judgment_policy.py:163-167`), and the UI labels it “非获胜概率” and displays `/ 100`, not `%` (`frontend/src/components/JudgmentPanel.tsx:32-36`). It is a presentation index, not a reported performance metric.

### C. Result existence and number matching: PASS

Training artifacts exist for all three candidates, and the training log records 28,738 real games, 15,717 training games, each fit, each validation/test result, and the selected source (`reports/aggressive/experiment_training.log:1-8`). The program report numbers match the CSV recomputation (`reports/aggressive/experiment_results.md:11-18`). Artifact, data, policy, evaluation, prediction, code, and report hashes all match their metadata/manifests; the full audited snapshot binds the runtime and frontend (`reports/aggressive/AUDITED_SNAPSHOT.json:149-163`, `reports/aggressive/AUDITED_SNAPSHOT.json:301-341`, `reports/aggressive/AUDITED_SNAPSHOT.json:409-465`).

An intermediate `real_analysis.json` observed during review overstated one pair explanation by showing only the 101-game side. It was regenerated before this verdict. The final file now reports both sides, uses the minimum relevant evidence of 3 games, and marks the explanation `limited` (`reports/aggressive/real_analysis.json:925-946`). This is resolved in the audited snapshot.

### D. Metric execution and dead code: PASS

The training path calls `metrics` for raw and calibrated validation/calibration/test predictions and cohort metrics (`src/worlds_predictor/enhanced_training.py:55-78`), calls both paired ranking and day-block loss bootstraps (`src/worlds_predictor/enhanced_training.py:145-150`), and the judgment evaluator calls `metrics`, `build_policy`, `apply_policy`, and `evaluate_frame` on selected, baseline, Worlds, patch, league, and patch cohorts (`scripts/evaluate_aggressive.py:34-66`, `scripts/evaluate_aggressive.py:76-125`). Their outputs appear in the saved JSON and CSV files.

### E. Scope assessment: WARN

The experiment uses one fixed seed (`configs/aggressive_experiment.json:6`) and one temporal split. The 2026 holdout was inspected in an earlier phase, so all test comparisons are retrospective rather than fresh confirmation (`reports/aggressive/experiment_results.md:5-7`, `reports/aggressive/experiment_results.md:24-26`). The selected model's day-block comparison explicitly says one seed and a previously inspected holdout (`reports/aggressive/experiment_metrics.json:19817-19829`). The Worlds target cohort is 22 maps, with a 95% Wilson interval of roughly 47.3% to 83.6% for its 15/22 hit rate (`reports/aggressive/judgment_evaluation.json:598-634`). Current wording stays within that evidence; broader generalization, robust-improvement, or event-reliability claims would exceed it.

### F. Evaluation classification: PASS — `real_gt`

Both experiment and judgment reports declare `real_gt` (`reports/aggressive/experiment_metrics.json:2-4`, `reports/aggressive/judgment_evaluation.json:2-12`), and the label path above confirms that classification.

## Additional integrity checks

### Temporal isolation: PASS

Dataset reads require both `date < as_of` and `available_at < as_of` (`src/worlds_predictor/data.py:386-405`). Feature construction updates state only when a prior result's `available_at` is strictly earlier than the target game (`src/worlds_predictor/features.py:256-278`, `src/worlds_predictor/enhanced_features.py:151-163`). Inference also removes the target game and clamps history to the earlier of `as_of` and target date (`src/worlds_predictor/features.py:281-293`, `src/worlds_predictor/enhanced_features.py:166-180`). Request validation requires `as_of <= scheduled_start` (`src/worlds_predictor/schemas.py:54-64`). The remaining caveat is correctly disclosed: actual historical publication timestamps are unavailable, so `available_at` is a conservative reconstruction (`reports/data_quality.json:207-209`).

### Source, model, and report consistency: PASS

The enhanced loader verifies the model artifact and trained feature-code hashes before deserialization (`src/worlds_predictor/enhanced.py:18-37`). The decision loader binds policy, evaluation, policy code, model version, and model artifact (`src/worlds_predictor/judgment_policy.py:188-224`; `reports/aggressive/judgment_manifest.json:3-12`). `AUDITED_SNAPSHOT.json` additionally binds the full runtime, frontend, reports, models, and logs. These are trusted-local integrity hashes, not external signatures.

### Pair-feature semantics: PASS

Mid/jungle and bot/support features are keyed by explicit roles plus champion or player IDs, with separate full-history, recent, patch, and player-pair observations (`src/worlds_predictor/enhanced_features.py:19`, `src/worlds_predictor/enhanced_features.py:95-101`). Explanations use both sides' matching role pair and the minimum sample size (`src/worlds_predictor/judgment.py:88-93`). The final real replay correctly reports blue 3 games and red 101 games, then marks the grouped evidence limited (`reports/aggressive/real_analysis.json:925-946`). These are observed co-appearance/outcome associations, not tactical synergy ratings.

### No fabricated advantages, risks, or tactical ratings: PASS

Positive reasons and risks come from signed full-vector SHAP groups. Missing reasons are explicit evidence gaps; missing risks become two distinct unmodeled/evidence-gap statements rather than invented triggers (`src/worlds_predictor/judgment.py:157-177`). Unsupported crowd-control, engage, phase-curve, and team-style features were predeclared (`reports/aggressive/experiment_protocol.json:43-52`) and are omitted from output as ratings (`src/worlds_predictor/analysis.py:249-260`).

### Judgment-source failure preserves standard output: PASS

The optional judgment layer catches missing, corrupt, incompatible, or failed enhanced-source conditions and returns an unavailable judgment while preserving the standard calibrated result (`src/worlds_predictor/judgment.py:197-252`). Backend tests assert that the original result is unchanged (`tests/test_judgment.py:87-107`), and the UI keeps the standard probability visible when judgment is unavailable (`frontend/src/components/AnalysisPanel.tsx:42-44`).

## Claim impact

- **Actual enhanced training was attempted/completed:** supported.
- **Explicit winner, evidence, and non-probability support index are implemented:** supported.
- **Overall ranking/performance improvement over the frozen model:** unsupported. Selected-minus-frozen test deltas are accuracy `-0.0031153`, ROC-AUC `-0.0056066`, log loss `+0.0031355` (worse), and Brier `+0.0013334` (worse).
- **Strong-call improvement:** unsupported. The selected strong group is 2,072/2,697 (`76.83%`), while the frozen policy's different strong group is 2,080/2,666 (`78.02%`). These are different ECDF-selected cohorts and do not constitute a paired improvement test.
- **Strong-group hit rates:** supported only as descriptive retrospective subgroup results.
- **Worlds-specific reliability:** unsupported; 22 maps are too few.

## Action items

1. Keep overall and strong-call improvement claims out of product and research conclusions; preserve the current explicit negative comparison.
2. For a performance claim, preregister and evaluate newly collected post-cutoff matches that have never been inspected, with multiple seeds and multiple temporal cutoffs.
3. Compare strong-call behavior with paired coverage/risk analysis on a common cohort and account for day/series clustering.
4. Accumulate a materially larger Worlds cohort before making event-specific accuracy or calibration claims.
5. Preserve and regenerate the delivery manifest whenever runtime sources, reports, or models change.

## Acceptance status

This is a fresh same-family Codex review. Its semantic verdict is **provisional**, not cross-family acceptance. The deterministic file/hash/value checks establish evidence existence and consistency only; they do not upgrade the claim judgment.
