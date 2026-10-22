# Phase 2 — local BP analysis workbench

## Boundary and existing evidence

Reuse the frozen phase-1 CatBoost artifacts from run `20261022T093531Z-f5eb82ee9db3`. Do not retrain or rewrite its datasets, feature implementation, metrics or audit. Phase-2 source and integration evidence are separate. Existing model integrity checks continue to verify the feature implementation and artifact hashes.

The initial live preflight loaded the existing model and exercised a real prediction. There are 28,738 accepted historical games; the independently held-out set contains 9,309 games. The exact Worlds + target patch slice has only 22 games. All reliability claims retain these scope limits.

## Architecture

- `frontend/`: React, strict TypeScript, Vite, Tailwind, Zustand and Recharts. All API requests use `/api`, proxied to FastAPI during local development. No cloud accounts or paid services.
- Existing `/predict`, `/health` and `/players` remain compatible.
- New `/catalog`, `/teams`, `/teams/{id}/roster`, `/matches` read versioned external reference metadata and strictly time-bounded real history.
- New `/analyze` provides real pre/post-BP model probabilities, point-in-time raw historical statistics, native CatBoost SHAP values and explicit scope limitations.
- Browser local storage holds draft state and immutable prediction snapshots. Changes to inputs invalidate the current result. Historical results retain original model version, cutoff and probabilities even after model upgrades.

## Public inputs and truth boundaries

Inputs preserve the phase-1 PredictionRequest plus a separate draft-context object for local Bo3/Bo5 restrictions. No series win probability is produced. Map side and draft first-pick entitlement remain independent. The current phase-1 model does use first-pick as a categorical input.

Champions are sourced from Riot Data Dragon 16.20.1 in Chinese and English; names normalize to the dataset's English identifiers. Roles shown by the picker are observed historical usage, not a hardcoded claim about champion strength. Missing historical samples display unknown/null and an explicit low-sample label.

Worlds participants and applicable Fearless rules require recorded primary-source evidence. An observed historical lineup is labeled with its actual observation date and is never silently called the current registered starting lineup. Unverified team-logo permission results in a neutral initials badge, not a fabricated or copied logo.

## Model comparison and explanation

The pre-BP comparison uses the actual saved B CatBoost artifact and the post-BP comparison uses the deployed C uniform-weight CatBoost artifact. These use common chronological split definitions but differ in features, training weights and fitted calibration parameters. The probability delta is an observational model comparison, not a causal BP effect.

Native CatBoost SHAP contributions explain the raw model log-odds; the displayed calibrated probability also passes through the separately fitted sigmoid calibrator. Raw empirical champion/player/matchup/synergy statistics are a distinct section. Unvalidated early/late-game, damage-mix, engage, peel and crowd-control ratings will not be invented.

## UX and verification

Chinese dark analysis workspace, blue/red team panels, gold accents, searchable portrait picker, independent ban slots, clear loading/errors, no result before a real API response. Draft completeness, duplicate selections, banned champions and verified Fearless restrictions are enforced client-side and server-side.

Vitest covers draft/history/persistence invariants; Pytest covers mappings, point-in-time statistics and real-model analysis; Playwright exercises the working UI in Chromium and WebKit, with screenshots at desktop and mobile sizes. WebKit is a Safari-engine compatibility check, not a claim that macOS Safari itself was tested unless it is actually exercised.

Riot attribution and non-endorsement text remain visible. This local research tool has no betting, wagering or gambling recommendation functionality. Any public distribution must separately satisfy the developer registration requirements documented in the source policy evidence.
