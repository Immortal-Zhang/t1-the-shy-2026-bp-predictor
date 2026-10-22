import type { Judgment, JudgmentEvidence } from './types'

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null
const number = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const fraction = (value: unknown): value is number => number(value) && value >= 0 && value <= 1
const nullableFraction = (value: unknown) => value === null || fraction(value)
const count = (value: unknown) => number(value) && value >= 0 && Number.isInteger(value)
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string')
const side = (value: unknown) => value === 'blue' || value === 'red'
const textKeys = (value: Record<string, unknown>, keys: string[]) => keys.every(key => typeof value[key] === 'string')

function evidence(value: unknown): value is JudgmentEvidence {
  return object(value) && textKeys(value, ['title', 'detail', 'category']) &&
    (value.contribution === null || number(value.contribution)) && strings(value.feature_names) &&
    (value.sample_games === null || count(value.sample_games)) && ['model', 'limited', 'unavailable'].includes(String(value.evidence_status))
}

function performance(value: unknown) {
  return object(value) && count(value.n) && nullableFraction(value.accuracy) && fraction(value.coverage) && nullableFraction(value.wilson_low) && nullableFraction(value.wilson_high)
}

/** Protect API results and locally persisted snapshots from incomplete evidence. */
export function isJudgment(value: unknown): value is Judgment {
  if (!object(value)) return false
  if (value.available === false) return typeof value.reason === 'string'
  if (value.available !== true || !textKeys(value, ['version', 'model_version']) || !['enhanced', 'frozen'].includes(String(value.engine))) return false
  const { winner, support, advantage, bp_assessment: bp, driver, reliability, evaluation } = value
  return object(winner) && side(winner.side) && typeof winner.team_id === 'string' && typeof winner.tie_break === 'boolean' &&
    object(support) && number(support.blue) && number(support.red) && support.blue >= 0 && support.blue <= 100 && support.red >= 0 && support.red <= 100 && Math.abs(support.blue + support.red - 100) < 1e-6 &&
    typeof support.definition === 'string' && number(support.raw_margin) && count(support.reference_n) && typeof support.out_of_reference_range === 'boolean' && fraction(support.judgment_calibrated_probability) &&
    object(advantage) && ['slight', 'clear', 'strong'].includes(String(advantage.key)) && typeof advantage.label === 'string' && typeof advantage.strong_validated === 'boolean' &&
    Array.isArray(value.reasons) && value.reasons.length === 3 && value.reasons.every(evidence) && Array.isArray(value.risks) && value.risks.length === 2 && value.risks.every(evidence) &&
    object(bp) && (bp.favored_side === null || side(bp.favored_side)) && typeof bp.label === 'string' && number(bp.net_contribution) && evidence(bp.weakness) &&
    object(driver) && ['bp', 'players_teams', 'context'].includes(String(driver.primary)) && textKeys(driver, ['label', 'note']) && [driver.bp_share, driver.players_teams_share, driver.context_share].every(fraction) &&
    object(reliability) && ['low', 'medium', 'high'].includes(String(reliability.level)) && typeof reliability.label === 'string' && strings(reliability.details) &&
    object(evaluation) && count(evaluation.n) && fraction(evaluation.accuracy) && performance(evaluation.strong) && textKeys(evaluation, ['scope', 'comparison_note']) &&
    Array.isArray(evaluation.grades) && evaluation.grades.every(row => performance(row) && object(row) && textKeys(row, ['key', 'label'])) && strings(value.limitations)
}
