import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, ArrowRight, BarChart3, Clock3, Database, Info, Save, ShieldCheck } from 'lucide-react'
import type { AnalyzeResponse, Champion } from '../types'
import { parseApiDate } from '../domain'
import { usePredictorStore } from '../store'
import { JudgmentPanel, JudgmentTechnical } from './JudgmentPanel'
import { ModeSwitch } from './ModeSwitch'

const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const date = (value: string | null | undefined) => value ? parseApiDate(value).toLocaleString('zh-CN', { hour12: false }) : '暂无记录'
const roles: Record<string, string> = { top: '上单', jng: '打野', mid: '中单', bot: '下路', sup: '辅助' }

export function AnalysisPanel({ result, champions, blueName, redName, onSave, saved }: {
  result: AnalyzeResponse | null; champions: Champion[]; blueName: string; redName: string; onSave: () => void; saved: boolean
}) {
  const [tab, setTab] = useState<'overview' | 'players' | 'draft'>('overview')
  const mode = usePredictorStore(state => state.displayMode)
  const champion = (name: string) => champions.find(item => item.name_en === name || item.id === name)
  if (!result) return <section className="analysis-awaiting" aria-label="预测分析待生成"><ModeSwitch/><div className="empty-analysis panel">
    <div className="empty-orbit"><BarChart3 size={26} /></div>
    <div><p className="eyebrow">THE NEXT MOVE</p><h2>明确的判断，来自真实证据。</h2><p>完成双方 BP 后，查看预测胜者、支持指数、三个核心依据与两个风险。</p></div>
    <span className="quiet-tag">未请求模型 · 无预设胜率</span>
  </div></section>
  const p = result.prediction
  const comp = result.comparison
  const metrics = result.evaluation
  const contributions = result.explanation.contributions.slice(0, 9).map(item => ({ ...item, shortLabel: item.label || item.feature }))
  const judgment = result.judgment
  const probabilityHero = <div className="result-hero panel">
      <div className="result-context"><span><ShieldCheck size={14} />{p.selected_model}</span><span>单局预测 / 蓝红视角</span><span className="mono">{p.model_version}</span></div>
      <div className="probability-head"><div className="blue-text"><span>{blueName || '蓝色方'}</span><strong data-testid="blue-probability">{percent(p.blue_win_probability)}</strong></div><div className="versus-small">预计获胜概率<br/><b>VS</b></div><div className="red-text"><span>{redName || '红色方'}</span><strong data-testid="red-probability">{percent(p.red_win_probability)}</strong></div></div>
      <div className="probability-track" aria-label={`蓝方 ${percent(p.blue_win_probability)}，红方 ${percent(p.red_win_probability)}`}><div className="probability-blue" style={{ width: `${p.blue_win_probability * 100}%` }} /><div className="probability-red" style={{ width: `${p.red_win_probability * 100}%` }} /></div>
      <div className="result-footnote"><span><Clock3 size={13}/>历史数据截止 {date(p.data_cutoff)}</span><span><Database size={13}/>赛前历史 {p.sample_coverage.history_games.toLocaleString()} 局</span><span>概率估计，不是赛果承诺</span></div>
      <div className="coverage-row"><span>同联赛历史 <b>{p.sample_coverage.league_history_games}</b> 局</span><span>同版本历史 <b>{p.sample_coverage.patch_history_games}</b> 局</span><span>缺失 ban <b>{p.sample_coverage.missing_ban_slots}</b> 项</span><span>未知战队 <b>{p.sample_coverage.unknown_teams.length}</b> · 选手位置 <b>{p.sample_coverage.unknown_players_in_role.length}</b> · 英雄位置 <b>{p.sample_coverage.unknown_champions_in_role.length}</b></span></div>
      {(p.sample_coverage.patch_history_games === 0 || p.sample_coverage.unknown_teams.length > 0 || p.sample_coverage.unknown_players_in_role.length > 0 || p.sample_coverage.unknown_champions_in_role.length > 0) && <p className="coverage-warning"><Info size={12}/>部分输入缺少赛前历史；模型使用已训练的未知类别与平滑机制。该结果的数据覆盖较弱，请结合下方样本数量理解。</p>}
      <p className="tiny-copy">原始模型回测：Log Loss {metrics.log_loss.toFixed(4)} · Brier Score {metrics.brier_score.toFixed(4)} · {metrics.n.toLocaleString()} 局。数据可靠性不随展示模式改变。</p>
    </div>
  return <section className="analysis-section" data-testid="analysis-result">
    <div className="section-heading"><div><p className="eyebrow">MODEL INSIGHTS</p><h2>{mode === 'standard' ? '胜率与阵容洞察' : '胜者判断与阵容洞察'} <span className="pill gold">{saved ? '历史快照' : '真实模型结果'}</span></h2></div><button className="button subtle" onClick={onSave}><Save size={15} />保存预测</button></div>
    <ModeSwitch/>
    {mode !== 'standard' && (judgment?.available ? <JudgmentPanel judgment={judgment} mode={mode} blueName={blueName} redName={redName}/> : <div className="judgment-unavailable panel" role="status"><Info size={18}/><div><b>{judgment ? '激进判断当前不可用' : '此历史快照尚无激进判断'}</b><p>{judgment && !judgment.available ? judgment.reason : '保留当时的原始校准概率；不会用新算法改写旧记录。重新预测后可生成本次判断。'}</p><p>下方保留标准模型结果。</p></div></div>)}
    {mode === 'standard' || !judgment?.available ? probabilityHero : <details className="calibrated-technical panel"><summary><Info size={15}/>技术详情：原始校准概率、支持指数定义与回测</summary>{probabilityHero}<JudgmentTechnical judgment={judgment}/></details>}
    {mode === 'standard' && judgment?.available && <details className="calibrated-technical panel"><summary><Info size={15}/>技术详情：激进判断模型、支持指数与真实回测</summary><JudgmentTechnical judgment={judgment}/></details>}
    <div className="tabs analysis-tabs" role="tablist" aria-label="分析内容"><button role="tab" aria-selected={tab === 'overview'} className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>胜率对比与解释</button><button role="tab" aria-selected={tab === 'players'} className={tab === 'players' ? 'active' : ''} onClick={() => setTab('players')}>选手与英雄熟练度</button><button role="tab" aria-selected={tab === 'draft'} className={tab === 'draft' ? 'active' : ''} onClick={() => setTab('draft')}>对线与阵容协同</button></div>
    {tab === 'overview' && <div className="analysis-grid">
      <div className="panel analysis-card"><div className="card-heading"><h3><Activity size={16}/>标准模型 BP 前后对比</h3><span className="quiet-tag">蓝方视角</span></div>
        <div className="comparison-line"><div><small>战队 + 选手模型</small><strong>{percent(comp.pre_bp.blue_probability)}</strong><span>{comp.pre_bp.model}</span></div><ArrowRight className="comparison-arrow" size={22}/><div><small>完整 BP 模型</small><strong className="gold-text">{percent(comp.post_bp.blue_probability)}</strong><span>{comp.post_bp.model}</span></div></div>
        <div className="delta-row"><span>模型概率差</span><b className={comp.delta_blue >= 0 ? 'blue-text' : 'red-text'}>{comp.delta_blue >= 0 ? '+' : ''}{(comp.delta_blue * 100).toFixed(2)} <small>个百分点</small></b></div>
        <p className="note"><Info size={14}/>{comp.limitation}</p>
        <div className="metric-strip"><div><small>独立测试准确率</small><b>{percent(metrics.accuracy)}</b></div><div><small>ROC-AUC</small><b>{metrics.roc_auc?.toFixed(3) ?? '—'}</b></div><div><small>测试场次</small><b>{metrics.n?.toLocaleString() ?? '—'}</b></div></div>
        <p className="tiny-copy">全联赛回测不等于 Worlds 专项表现。目标版本 Worlds 样本仅 {metrics.worlds_target?.n ?? '—'} 局。</p>
      </div>
      <div className="panel analysis-card"><div className="card-heading"><h3><BarChart3 size={16}/>标准模型的主要特征贡献</h3><span className="quiet-tag">CatBoost SHAP</span></div>
        <div className="shap-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={contributions} layout="vertical" margin={{ top: 4, bottom: 4, left: 0, right: 20 }}><CartesianGrid horizontal={false} stroke="#243040"/><XAxis type="number" tickFormatter={(value: number) => Number(value).toFixed(2)} tickCount={6} domain={[(minimum: number) => Math.min(0, minimum), (maximum: number) => Math.max(0, maximum)]} tick={{ fill: '#8491a5', fontSize: 10 }} axisLine={false} tickLine={false}/><YAxis type="category" dataKey="shortLabel" width={150} tick={{ fill: '#c2ccda', fontSize: 10 }} axisLine={false} tickLine={false}/><Tooltip cursor={{ fill: '#ffffff06' }} contentStyle={{ background: '#141e2d', border: '1px solid #334158', borderRadius: 10, color: '#e4ebf6' }} formatter={value => [Number(value).toFixed(4), '原始 log-odds 贡献']}/><ReferenceLine x={0} stroke="#63758d"/><Bar dataKey="contribution" radius={[3, 3, 3, 3]} barSize={12}>{contributions.map(item => <Cell key={item.feature} fill={item.contribution >= 0 ? '#58a9ff' : '#ef7186'}/>)}</Bar></BarChart></ResponsiveContainer></div>
        <p className="tiny-copy">此图解释原始标准模型，显示绝对贡献最大的 9 项；未展示项不代表零。蓝色推动蓝方，红色推动红方。数值为校准前 log-odds，不是概率百分点或确定性原因；激进判断的证据见上方技术详情。</p>
      </div>
    </div>}
    {tab === 'players' && <div className="panel table-panel"><div className="card-heading"><h3>所选英雄的真实历史样本</h3><span className="quiet-tag">仅统计 as_of 之前已知赛果</span></div><div className="table-scroll"><table><thead><tr><th>选手 / 位置</th><th>所选英雄</th><th>使用场次</th><th>历史胜率</th><th>近期同英雄</th><th>最近使用</th><th>样本情况</th></tr></thead><tbody>{result.players.map(item => { const hero = champion(item.champion); return <tr key={`${item.side}-${item.role}`}><td><span className={`side-dot ${item.side}`}/><b>{item.name || item.player_id.slice(0, 12)}</b><small className="table-sub">{roles[item.role]} · 职业历史 {item.player_history_games} 局 · 近期 {percent(item.player_recent_win_rate)}</small></td><td><span className="table-champion">{hero && <img src={hero.image_url} alt=""/>}{hero?.name_zh || item.champion}</span></td><td>{item.games}</td><td>{percent(item.win_rate)}</td><td>{percent(item.recent_win_rate)}<small className="table-sub">{item.recent_games} 局样本</small></td><td className="small-cell">{date(item.last_played)}</td><td><span className={`pill ${item.sample_status !== 'sufficient' ? 'warning' : 'neutral'}`}>{item.sample_status !== 'sufficient' ? '历史样本不足' : `${item.games} 局已观测`}</span></td></tr> })}</tbody></table></div></div>}
    {tab === 'draft' && <div className="analysis-grid"><div className="panel analysis-card"><div className="card-heading"><h3>同位置对线历史</h3><span className="quiet-tag">独立历史统计</span></div><div className="matchup-list">{result.matchups.map(item => <div className="matchup" key={item.role}><span className="role-code">{item.role.toUpperCase()}</span><span>{champion(item.blue_champion)?.name_zh || item.blue_champion}</span><span className="muted">VS</span><span>{champion(item.red_champion)?.name_zh || item.red_champion}</span><b>{percent(item.blue_win_rate)}</b><small>{item.games} 局{item.sample_status !== 'sufficient' ? ' · 样本不足' : ''}</small></div>)}</div><p className="tiny-copy">比例为该英雄对线组合所在蓝方阵容的比赛胜率；不是单独对线胜率，也不能单独归因于英雄克制。</p></div>
      <div className="panel analysis-card"><div className="card-heading"><h3>两两英雄组合</h3><span className="quiet-tag">独立历史统计</span></div><div className="synergy-list">{result.synergies.map((item, index) => <div key={`${item.side}-${index}`}><span className={`side-dot ${item.side}`}/><span>{item.champions.map(name => champion(name)?.name_zh || name).join(' + ')}</span><b>{percent(item.win_rate)}</b><small>{item.games} 局{item.sample_status !== 'sufficient' ? ' · 样本不足' : ''}</small></div>)}</div><p className="tiny-copy">前后期、伤害构成、开团、保护与控制评分尚未验证，当前不展示推断分数。</p></div></div>}
    <details className="limitations panel"><summary><Info size={15}/>适用范围、校准与缺失数据说明</summary><ul>{[...result.limitations, ...p.warnings].map((item, index) => <li key={index}>{item}</li>)}</ul><p>模型训练标签截止：{date(p.model_label_cutoff)} · 请求时点：{date(p.as_of)}</p></details>
  </section>
}
