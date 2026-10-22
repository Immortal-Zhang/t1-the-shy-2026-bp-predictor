# Program-generated real-data evaluation

Run: `20261022T093531Z-f5eb82ee9db3`

Frozen estimators; sequential historical features updated only after earlier results become available. Separate validation model selection, calibration and independent test.

| Model | Validation LL | Test accuracy | Test AUC | Test LL | Test Brier | Test ECE |
|---|---:|---:|---:|---:|---:|---:|
| A_logistic | 0.65521 | 0.59523 | 0.62703 | 0.66592 | 0.23671 | 0.02242 |
| B_logistic | 0.67737 | 0.63734 | 0.68578 | 0.63512 | 0.22248 | 0.00841 |
| C_logistic | 0.72437 | 0.62692 | 0.67408 | 0.64198 | 0.22568 | 0.01524 |
| A_catboost | 0.66993 | 0.58610 | 0.61824 | 0.67049 | 0.23891 | 0.02073 |
| B_catboost | 0.64868 | 0.63304 | 0.68429 | 0.63766 | 0.22336 | 0.01462 |
| C_catboost | 0.64953 | 0.63541 | 0.69005 | 0.63587 | 0.22267 | 0.03697 |
| C_catboost_uniform | 0.64597 | 0.63949 | 0.69765 | 0.63017 | 0.22015 | 0.03134 |

Deployment: **C_catboost_uniform**, chosen using validation only.

## B versus C
- logistic: C−B test log loss 0.006862; day-block 95% interval [0.003618793748434365, 0.009890990977754649].
- catboost: C−B test log loss -0.001789; day-block 95% interval [-0.006160289666516462, 0.0016853731580317927].

## Event and patch coverage

- Worlds 2026: n=34, accuracy=0.61765, AUC=0.6070175438596491, Log Loss=0.69288. Small cohorts are descriptive only.
- Source 16.20 / public 26.20, all leagues: n=133, accuracy=0.67669, AUC=0.7031394275161588, Log Loss=0.63262. Small cohorts are descriptive only.
- Target intersection WLDs + source 16.20/public 26.20: n=22, accuracy=0.54545, AUC=0.5897435897435899, Log Loss=0.72044, Brier=0.26183, ECE=0.32262. This is too small to support reliable Worlds-specific accuracy or calibration.

## Limits

- One chronological holdout and one training seed; no accuracy guarantee or causal BP effect.
- Current downloadable snapshot cannot prove historical publication times; available_at is a conservative assumed outcome-availability boundary.
- Name-based local pro IDs are stable within registry, but source lacks independent player IDs; unresolved real-person ambiguities remain.
- C minus B bundles BP and patch; association is confounded by skill, opponent and draft selection.
- Per-league and unseen-league cohorts assess transport descriptively, not a dedicated leave-region-out experiment.
- Historical bans/first-pick values are used only as pregame metadata; timestamp availability of final BP is the caller's responsibility.
