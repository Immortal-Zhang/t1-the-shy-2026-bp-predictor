import { Crosshair, Gauge, Zap } from 'lucide-react'
import { usePredictorStore } from '../store'
import type { DisplayMode } from '../types'

const modes: { value: DisplayMode; name: string; description: string; icon: typeof Gauge }[] = [
  { value: 'standard', name: '标准模式', description: '展示原始校准概率', icon: Gauge },
  { value: 'aggressive', name: '激进模式', description: '明确胜者与模型证据', icon: Zap },
  { value: 'extreme', name: '极限判断', description: '先看结论、致命弱点与翻盘条件', icon: Crosshair },
]

export function ModeSwitch() {
  const mode = usePredictorStore(state => state.displayMode)
  const setMode = usePredictorStore(state => state.setDisplayMode)
  return <div className="judgment-mode-control">
    <div className="judgment-mode-switch" role="group" aria-label="预测展示模式">
      {modes.map(({ value, name, description, icon: Icon }) => <button key={value} type="button" aria-pressed={mode === value} className={mode === value ? 'active' : ''} title={description} onClick={() => setMode(value)} data-testid={`mode-${value}`}><Icon size={14}/><span>{name}</span>{value === 'aggressive' && <small>默认</small>}</button>)}
    </div>
    <p>{mode === 'standard' ? '标准模式保留原始校准概率。' : mode === 'extreme' ? '先给结论，再看失效条件；切换模式不会提高支持指数或改变校准概率。' : '明确选出胜者，按模型证据分级。支持指数不是获胜概率。'}</p>
  </div>
}
