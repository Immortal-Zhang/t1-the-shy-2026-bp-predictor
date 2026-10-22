# Phase-two targeted integration review

Date: 2026-10-22. Scope: backend reuse of the phase-one artifacts, draft validation, point-in-time catalog/statistics, frontend state invalidation, saved results and Fearless applicability. This is a same-team, implementation-aware review; the reviewer authored the analysis extension, so it is not an independent external model audit. Phase-one fitting and its published scores were not re-audited or changed here.

## Conclusion

The reviewed website path uses the existing real B/C CatBoost artifacts and does not synthesize win probabilities. Material integration issues identified during review were fixed and their relevant checks passed. Remaining qualifications are data/model scope and browser verification scope, not evidence of fabricated inference.

## Material findings and resolutions

1. **Future roster statistics could survive a changed `as_of` — fixed.** Previously, changing the cutoff retained the prior roster's IDs, observed date and historical form. `frontend/src/store.ts:112-122` now clears roster-derived IDs, names, statistics and observation metadata when the instant changes, while preserving the user's champion/ban draft for re-confirmation. Equivalent timezone representations do not incorrectly clear evidence. Regression coverage is in `frontend/src/store.test.ts:52-71`.
2. **Official participation could be shown before its announcement — fixed.** An initial live read at `2026-01-01T00:00:00Z` returned 17 future-qualified teams. `src/worlds_predictor/catalog.py:96-120` now applies a strict conservative availability boundary; a date-only October 5 publication is available only after October 6 00:00 UTC. Both team flags/names and catalog participant counts obey that boundary (`catalog.py:136-188`). Independent checks returned zero at January 1 and exactly at the boundary, and 19 after the boundary. This remains a current source snapshot, not a reconstructed historical publication archive.
3. **Worlds Fearless rules could be claimed for arbitrary leagues — fixed.** `src/worlds_predictor/analysis.py:76-91` restricts verified enforcement to a recognized Worlds league in 2026 and a supported Bo3/Bo5 format. Other events return a validation error rather than inheriting unverified rules. The UI labels the switch as Worlds-specific and disables it outside its supported scope.
4. **Previously picked Fearless champions were blocked for picks but accepted as current bans — fixed.** The editor/API now consistently reject unavailable prior picks in either current picks or bans (`analysis.py:92-107`). The official international rules distinguish erroneous unavailable picks and bans in §§4.5.6–4.5.7. This editor prevents those errors; it does not implement the officials' restart/adjudication procedure or output a series probability.
5. **Sample sufficiency and symmetric draft presentation were inconsistent — fixed.** The backend returns `none/limited/sufficient` with a 20-game descriptive threshold. The UI formerly used a separate five-game cutoff and truncated the 20 synergy pairs after 12, disproportionately hiding red-side pairs. `frontend/src/components/AnalysisPanel.tsx:47-49` now uses the returned sample status and displays all 20 pairs. This threshold is a disclosure convention, not proof of statistical reliability.
6. **Roster request races could overwrite edits or cancel the opposite side — fixed.** `frontend/src/App.tsx:37-38,92-104` now uses per-side request counters and checks the unchanged side snapshot and cutoff before applying a response. Opposite-side requests no longer invalidate each other; manual changes/reset/swap are not overwritten by an older response. The implementation was inspected; dedicated delayed-network browser regression remains part of the owner's end-to-end verification scope.

## Prediction and evidence checks

- `/analyze` is integrated through `create_analysis_router`; no separate model was trained for the UI (`src/worlds_predictor/api.py`, `analysis_api.py`).
- Selected C and pre-BP B artifacts must match the phase-one per-run evaluation hashes, and the feature code must match the trained hash before deserialization (`analysis.py:112-135`). The existing phase-one prediction function continues to enforce its trained-label cutoff.
- Hero aliases are resolved from the pinned verified Data Dragon catalog, followed by a second complete request validation. English/Chinese aliases cannot bypass duplicate-pick or pick/ban conflicts (`analysis.py:54-73`). Unknown heroes fail rather than receive a fabricated rating.
- Historical observations are loaded through the existing storage-level cutoff and the target `game_id` is excluded. Player/champion statistics, role matchups and both sides' pair counts use only that historical frame. A test injecting a 2027 outcome did not change the real 2026 prediction, comparison or descriptive statistics (`tests/test_analysis.py`).
- Zero sample rates are `null`, with zero counts and no fabricated 50% value. Recent hero/player form is based on the latest 20 eligible observations, not current-game KDA or economy.
- Native CatBoost SHAP reconstructs the selected model's uncalibrated blue-side raw log-odds. The actual replay reconstruction error was `8.881784197001252e-16`; the UI labels the units and rejects a causal interpretation. Final probabilities are separately calibrated.
- Actual replay before-BP blue probability: `0.3538980344286181`; after-BP: `0.30217792358429685`; difference: `-0.051720110844321265`. Both came from verified local models. The comparison discloses the differing training weights and cannot isolate the causal effect of BP (`reports/phase2/real_analysis.json`).
- Input edits invalidate a displayed result, asynchronous inference responses require the original input revision, and saved snapshots retain their original response/model metadata. Actual results entered in the browser are labelled manual and are not passed back as model features (`frontend/src/store.ts`, `App.tsx`).

## Checks executed by this review

- `pytest tests/test_analysis.py -q`: **22 passed**, one upstream Starlette/httpx deprecation warning (`reports/phase2/analysis_tests.log`). Includes actual model loading, real HTTP prediction consistency, missing-model 503, invalid input 422, alias validation, as-of invariance, native SHAP and Fearless scope.
- `pytest tests/test_catalog.py -q`: **23 passed**, same upstream warning (`reports/phase2/review_catalog_tests.log`). Includes roster/date boundaries, qualification publication boundaries and non-result replay requests.
- `PATH="/opt/homebrew/bin:$PATH" npm exec vitest run src/store.test.ts src/domain.test.ts`: **39 passed** (`reports/phase2/review_state_tests.log`). The default PATH selected ChatGPT's embedded `cua_node`, which could not load Rolldown's native binding; the installed Homebrew Node succeeded. No dependency deletion/reinstallation was performed by the reviewer.
- These targeted checks do not replace the owner's complete frontend build, backend suite or Playwright/UI checks. This review did not independently run native Safari or Chrome. Chromium/WebKit engine tests, if used by the owner, should be described as such rather than claimed as native Safari-app certification.

## Remaining bounds and follow-up

- Only 22 independent-test games match Worlds plus its target patch; current results do not demonstrate reliable event-specific accuracy/calibration or stable BP gain.
- Automatic rosters are explicitly the latest observed actual lineup before the cutoff, not verified current starters or a complete official registered roster. Name-derived professional IDs and dated aliases still require human/source identity verification.
- Team marks without a verified reusable asset source are intentionally replaced by neutral abbreviation badges. These must not be described as licensed official logos.
- Patch namespace conversion is the reviewed public 26.20/source 16.20 pair only. Other public patch names can be unseen categories in custom research mode; expose per-request patch/entity coverage prominently rather than implying broad version validation.
- Native SHAP explains the model, not why a team necessarily wins. Historical matchup and synergy win rates are confounded by team/player strength and draft selection.
- Front/back-game strength, damage mix, engage, protection and control scores are not verified features in the current model and remain explicitly unavailable. There is no validated Bo3/Bo5 outcome model.
- The publication and result availability boundaries are conservative assumptions over downloaded snapshots, not a real-time vendor archive. Official event rules may change after the recorded snapshot.
