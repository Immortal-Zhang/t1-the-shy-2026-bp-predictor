# Phase 2 — executed validation

Generated: 2026-10-22T11:47:54.702940+00:00

| Check | Actual result |
|---|---|
| Pytest | 219 passed; one upstream deprecation warning |
| Vitest | 44 passed |
| Strict TypeScript + production build | Passed; dynamically split analysis chart bundle |
| Full E2E | 12 passed across actual Chrome and Playwright WebKit |
| Production-build E2E | 4 passed; actual drafting and prediction/history flows repeated in both browsers |
| Cold start and existing-service reuse | Both commands executed successfully |
| Native macOS Safari 26.5 | Page load, model readiness and 22-match data observed; full native flow not claimed |

## Real model evidence

- Model: `20261022T093531Z-f5eb82ee9db3/C_catboost_uniform`
- Existing selected-model and feature hashes remain unchanged; no retraining.
- Independent all-league test: n=9309, accuracy=0.63949, AUC=0.69765, log loss=0.63017, Brier=0.22015.
- Target Worlds patch: only 22 maps; accuracy 0.54545, insufficient for event reliability.
- Production API returned blue=0.302177923584, red=0.697822076416 for an actual historical replay.
- E2E error injection only generated a 503 failure response, never a fake probability.

## Tested interactions

Team search and exact observed roster auto-fill; manual professional player selection; Chinese/English hero search; all ten roles; duplicate and ban guards; side swap; hero/BP reset; real prediction and explanations; persisted history and refresh; user-entered actual results; delete/clear; error and stale-response handling; Fearless restriction; desktop/mobile overflow checks.

## Limits

- No verified current starting-lineup feed; auto-fill is dated observed lineup.
- No licensed full team-logo set; initials badges used.
- Local professional IDs retain unverified person linkage.
- Only 22 target-event test maps; no reliable Worlds-specific accuracy claim.
- No validated series probability or early/late-game/engage/peel/damage/CC scores.
- Native Safari checked loading/data readiness only; complete flows executed in Chrome and WebKit.
