# Supplemental cross-league training-label sensitivity

Status: **blocked**

Fixed supplemental comparison of pooled C CatBoost labels against target-league-only C CatBoost labels. Same features, chronology, hyperparameters, seed, recency weights, and identical target-league held-out games. No test-driven tuning or deployment selection.

Globally pooled historical features are preserved in both arms. This is pooled training-label sensitivity, not complete region isolation.

Target league: LCK; calibrated comparison: True.

Pooled training games: 15717; target-league training games: 831.

| Split | Games | Blue wins |
|---|---:|---:|
| train | 831 | 437 |
| validation | 206 | 94 |
| calibration | 0 | 0 |
| test | 502 | 283 |

No model or comparison metrics were fabricated.

- calibration: 0 eligible games, requires 50
- calibration: requires both binary outcomes

## Limits

- Single target league, chronological holdout and random seed; results do not establish transport to every region or Worlds.
- League-only and pooled models use different training sample sizes and opposition coverage; effects are not causal.
- Globally derived team/player/champion history remains available to both models.
- This supplemental protocol was fixed before its league-only fit, after the main evaluation; it is exploratory evidence.
