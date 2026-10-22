import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { AnalysisPanel } from './AnalysisPanel'
import { usePredictorStore } from '../store'
import { analysisFixture, judgmentFixture } from '../test/fixtures'

vi.mock('recharts', () => {
  const Group = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  const Empty = () => null
  return { ResponsiveContainer: Group, BarChart: Group, Bar: Group, CartesianGrid: Empty, Cell: Empty, ReferenceLine: Empty, Tooltip: Empty, XAxis: Empty, YAxis: Empty }
})

beforeEach(() => {
  localStorage.clear()
  usePredictorStore.setState({ displayMode: 'aggressive' })
})

function renderAnalysis(kind: 'available' | 'legacy' | 'unavailable' = 'available') {
  const result = analysisFixture()
  result.prediction.blue_win_probability = 0.51
  result.prediction.red_win_probability = 0.49
  if (kind === 'available') result.judgment = judgmentFixture()
  if (kind === 'unavailable') result.judgment = { available: false, reason: 'Judgment artifact unavailable' }
  render(<AnalysisPanel result={result} champions={[]} blueName="Synthetic Blue" redName="Synthetic Red" onSave={vi.fn()} saved={kind === 'legacy'}/>)
  return result
}

describe('judgment presentation with synthetic unit fixtures only', () => {
  it('defaults to an explicit winner with separate support indices and evidence gaps', () => {
    renderAnalysis()
    expect(screen.getByTestId('mode-aggressive')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('predicted-winner')).toHaveTextContent('Synthetic Red')
    expect(screen.getByTestId('red-support')).toHaveTextContent('78/ 100')
    expect(screen.getByTestId('judgment-panel')).toHaveTextContent('非获胜概率')
    expect(screen.getAllByTestId('judgment-reason')).toHaveLength(3)
    expect(screen.getAllByTestId('judgment-risk')).toHaveLength(2)
    expect(screen.getByTestId('judgment-panel')).toHaveTextContent('第3项独立优势尚无证据')
    expect(screen.getByTestId('bp-assessment')).toHaveTextContent('BP 项支持蓝方')
    expect(screen.getByTestId('judgment-driver')).toHaveTextContent('主要依靠选手与战队历史')
    expect(screen.getByTestId('judgment-reliability')).toHaveTextContent('数据可靠性偏低')
  })
  it('does not alter scores, winner, grade or calibrated probability in extreme mode', async () => {
    const user = userEvent.setup()
    const original = renderAnalysis()
    const beforeIndex = screen.getByTestId('red-support').textContent
    const beforeGrade = screen.getByTestId('advantage-grade').textContent
    await user.click(screen.getByTestId('mode-extreme'))
    expect(screen.getByText('我判断 Synthetic Red 获胜。')).toBeVisible()
    expect(screen.getByTestId('red-support').textContent).toBe(beforeIndex)
    expect(screen.getByTestId('advantage-grade').textContent).toBe(beforeGrade)
    expect(screen.getByTestId('predicted-winner')).toHaveTextContent('Synthetic Red')
    expect(screen.getByTestId('blue-probability')).toHaveTextContent('51.0%')
    expect(original.prediction.blue_win_probability).toBe(0.51)
    const order = screen.getByTestId('judgment-panel').querySelector('.judgment-evidence-grid')
    expect(order?.firstElementChild?.classList.contains('judgment-risks')).toBe(true)
  })
  it('keeps raw calibrated odds in technical details and restores the standard view', async () => {
    const user = userEvent.setup()
    renderAnalysis()
    expect(screen.getByTestId('blue-probability')).not.toBeVisible()
    await user.click(screen.getByText('技术详情：原始校准概率、支持指数定义与回测'))
    expect(screen.getByTestId('blue-probability')).toBeVisible()
    expect(screen.getByTestId('blue-probability')).toHaveTextContent('51.0%')
    expect(screen.getByTestId('judgment-technical')).toHaveTextContent('38.0%')
    expect(screen.getByTestId('judgment-technical')).toHaveTextContent('SYNTHETIC STRUCTURAL TEST ONLY')
    expect(within(screen.getByTestId('judgment-technical')).getByText('样本不足')).toBeVisible()
    await user.click(screen.getByTestId('mode-standard'))
    expect(screen.queryByTestId('judgment-panel')).not.toBeInTheDocument()
    expect(screen.getByTestId('blue-probability')).toBeVisible()
    expect(screen.getByTestId('blue-probability')).toHaveTextContent('51.0%')
    expect(screen.getByTestId('red-probability')).toHaveTextContent('49.0%')
  })
  it('keeps old history snapshots readable without synthesizing new evidence', () => {
    renderAnalysis('legacy')
    expect(screen.getByText('此历史快照尚无激进判断')).toBeVisible()
    expect(screen.queryByTestId('predicted-winner')).not.toBeInTheDocument()
    expect(screen.getByTestId('blue-probability')).toBeVisible()
    expect(screen.getByText('历史快照')).toBeVisible()
  })
  it('shows a judgment service failure while preserving the valid standard result', () => {
    renderAnalysis('unavailable')
    expect(screen.getByText('激进判断当前不可用')).toBeVisible()
    expect(screen.getByText('Judgment artifact unavailable')).toBeVisible()
    expect(screen.queryByTestId('judgment-panel')).not.toBeInTheDocument()
    expect(screen.getByTestId('blue-probability')).toHaveTextContent('51.0%')
  })
})
