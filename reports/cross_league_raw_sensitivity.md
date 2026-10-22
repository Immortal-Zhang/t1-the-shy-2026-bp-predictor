# Supplemental cross-league training-label sensitivity

Status: **complete**

Fixed supplemental comparison of pooled C CatBoost labels against target-league-only C CatBoost labels. Same features, chronology, hyperparameters, seed, recency weights, and identical target-league held-out games. No test-driven tuning or deployment selection.

Globally pooled historical features are preserved in both arms. This is pooled training-label sensitivity, not complete region isolation.

Target league: LCK; calibrated comparison: False.

Pooled training games: 15717; target-league training games: 831.

| Split | Games | Blue wins |
|---|---:|---:|
| train | 831 | 437 |
| validation | 206 | 94 |
| calibration | 0 | 0 |
| test | 502 | 283 |

| Training labels | Test accuracy | AUC | Log loss | Brier | ECE |
|---|---:|---:|---:|---:|---:|
| Target league only | 0.61753 | 0.69355 | 0.67066 | 0.23406 | 0.11244 |
| Pooled, same test games | 0.59163 | 0.66442 | 0.66343 | 0.23481 | 0.08504 |

Pooled minus league-only log loss: -0.007230; day-block 95% interval [-0.04193490838182783, 0.027012229890486614].

## Limits

- Single target league, chronological holdout and random seed; results do not establish transport to every region or Worlds.
- League-only and pooled models use different training sample sizes and opposition coverage; effects are not causal.
- Globally derived team/player/champion history remains available to both models.
- This supplemental protocol was fixed before its league-only fit, after the main evaluation; it is exploratory evidence.
- No target-league games exist in the configured calibration block for this run; this separate raw-vs-raw comparison does not establish calibrated league-specific accuracy.
