import { describe, expect, it } from 'vitest'
import { isJudgment } from './judgment'
import { judgmentFixture } from './test/fixtures'

describe('judgment boundary validation', () => {
  it('accepts complete structural evidence or an explicit unavailable response', () => {
    expect(isJudgment(judgmentFixture())).toBe(true)
    expect(isJudgment({ available: false, reason: 'Artifact missing' })).toBe(true)
  })
  it.each([
    { support: { blue: 120, red: -20 } },
    { support: { blue: 78, red: 78 } },
    { reasons: [] },
    { risks: [] },
    { winner: { side: 'unknown' } },
    { reliability: null },
    { support: null },
  ])('rejects incomplete or impossible evidence %j', mutation => {
    const fixture = judgmentFixture()
    expect(isJudgment({ ...fixture, ...mutation })).toBe(false)
  })
})
