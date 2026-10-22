# Enhanced ranking experiment — real historical data

Run: `20261022T120914Z-enhanced`

Retrospective research holdout, previously inspected in phase 1; not fresh confirmatory evidence.

Selection: Maximum raw validation ROC-AUC among candidates with validation raw log loss <= frozen baseline + 0.01; must strictly improve baseline validation AUC to deploy.

Selected: **enhanced_recent90_d4**; the frozen standard model is unchanged.

|Model|Validation raw AUC|Validation raw Log Loss|Test accuracy|Test AUC|Test Log Loss|Test Brier|
|---|---:|---:|---:|---:|---:|---:|
|frozen_C|0.682842|0.645967|0.639489|0.697653|0.630171|0.220150|
|enhanced_uniform_d5|0.682478|0.645057|0.643893|0.699882|0.627146|0.218847|
|enhanced_recent180_d5|0.686003|0.638641|0.649694|0.701690|0.626687|0.218495|
|enhanced_recent90_d4|0.688390|0.641102|0.636373|0.692046|0.633306|0.221484|

The selected 90-day model improves validation AUC but not the previously inspected 2026 holdout. The 180-day candidate has better retrospective test scores, but was not selected because test metrics are excluded from model selection. No new generalization improvement is established.

190 added numeric features use only known earlier results: decayed team/player form, recent role-specific champion and matchup histories, same-patch player/champion and team histories, explicit mid/jungle and bot/support champion pairs and player pairs, identical-roster experience, and head-to-head outcomes. These are match win associations, not controlled measures of individual strength or tactical synergy.

Control/engage ratings, game-phase curves and team-style matchup labels remain unsupported by the validated standardized data. None was invented.

The calibration fit uses a separate 716-game block. Validation calibrated scores are retrospectively transformed by this later calibrator only to define judgment presentation; model selection uses uncalibrated validation AUC/log loss. Calibration-block scores are in-sample.

Future confirmation requires newly collected games after the existing data cutoff. All test cohorts and day-block intervals remain exploratory and one-seed.
