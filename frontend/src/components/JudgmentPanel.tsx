import { ArrowUpRight, Crosshair, Database, Info, ShieldAlert, Swords, Target, Trophy } from 'lucide-react'
import type { AvailableJudgment, DisplayMode, JudgmentEvidence, Side } from '../types'

const pct = (value: number | null) => value === null ? '样本不足' : `${(value * 100).toFixed(1)}%`
const sideLabel = (side: Side) => side === 'blue' ? '蓝方' : '红方'
const amount = (value: number) => value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })

function Evidence({ item, index, risk = false }: { item: JudgmentEvidence; index: number; risk?: boolean }) {
  return <li className={`judgment-evidence ${item.evidence_status}`} data-testid={risk ? 'judgment-risk' : 'judgment-reason'}>
    <span className="evidence-number">{risk ? <ShieldAlert size={15}/> : String(index + 1).padStart(2, '0')}</span>
    <div><h4>{item.title}</h4><p>{item.detail}</p><div className="evidence-meta">
      <span>{item.evidence_status === 'model' ? '真实模型证据' : item.evidence_status === 'limited' ? '证据有限' : '未建立证据'}</span>
      {item.sample_games !== null && <span>{item.sample_games.toLocaleString()} 局样本</span>}
    </div></div>
  </li>
}

export function JudgmentPanel({ judgment: j, mode, blueName, redName }: {
  judgment: AvailableJudgment; mode: Exclude<DisplayMode, 'standard'>; blueName: string; redName: string
}) {
  const winnerName = (j.winner.side === 'blue' ? blueName : redName) || sideLabel(j.winner.side)
  const bpName = j.bp_assessment.favored_side ? (j.bp_assessment.favored_side === 'blue' ? blueName : redName) || sideLabel(j.bp_assessment.favored_side) : null
  const reasons = <section className="judgment-reasons"><div className="judgment-card-title"><Target size={16}/><h3>三个核心判断依据</h3><span>按本场模型贡献排序</span></div><ol>{j.reasons.map((item, index) => <Evidence key={`${item.title}-${index}`} item={item} index={index}/>)}</ol></section>
  const risks = <section className="judgment-risks"><div className="judgment-card-title"><ShieldAlert size={16}/><h3>{mode === 'extreme' ? '判断失效的两个条件' : '最可能推翻判断的两个因素'}</h3></div><ol>{j.risks.map((item, index) => <Evidence key={`${item.title}-${index}`} item={item} index={index} risk/>)}</ol></section>
  return <div className={`judgment-panel panel ${mode} favors-${j.winner.side}`} data-testid="judgment-panel">
    <div className="judgment-topline"><span><Crosshair size={15}/>{mode === 'extreme' ? 'EXTREME CALL · 极限判断' : 'DECISIVE CALL · 激进判断'}</span><span>{j.engine === 'enhanced' ? '增强模型' : '已部署模型'} · 单局胜者判断</span><b className="experimental-label">实验性判断</b><span className={`reliability-badge ${j.reliability.level}`} data-testid="judgment-reliability"><Database size={12}/>{j.reliability.label}</span></div>
    <p className="judgment-experiment-note" data-testid="judgment-experiment-note">{j.evaluation.comparison_note}</p>
    <div className="judgment-headline">
      <div className="winner-block"><p>{mode === 'extreme' ? '本场结论' : '预测胜者'}</p><h2 className={`${j.winner.side}-text`} data-testid="predicted-winner"><Trophy size={29}/>{winnerName}<span>{sideLabel(j.winner.side)}</span></h2><p className="winner-verdict">{mode === 'extreme' ? `我判断 ${winnerName} 获胜。` : `我更看好 ${winnerName}。`}</p>{j.winner.tie_break && <p className="tie-notice">模型方向恰好持平；按预先声明的平局规则选边，没有领先证据。</p>}</div>
      <div className={`advantage-badge ${j.advantage.key}`}><span>综合倾向等级</span><b data-testid="advantage-grade">{j.advantage.label}</b><small>{j.advantage.key === 'strong' ? j.advantage.strong_validated ? '强倾向达到验证门槛' : '强倾向未通过验证门槛' : '等级依据验证期门槛'}</small></div>
    </div>
    <div className="support-heading"><span>双方支持指数 <small>SUPPORT INDEX</small></span><b>非获胜概率</b></div>
    <div className="support-numbers"><div className="blue-text"><span>{blueName || '蓝方'}</span><b data-testid="blue-support">{amount(j.support.blue)}<small>/ 100</small></b></div><ArrowUpRight size={20}/><div className="red-text"><span>{redName || '红方'}</span><b data-testid="red-support">{amount(j.support.red)}<small>/ 100</small></b></div></div>
    <div className="support-track" aria-label={`蓝方支持指数 ${amount(j.support.blue)}，红方支持指数 ${amount(j.support.red)}，不是获胜概率`}><div className="probability-blue" style={{ width: `${j.support.blue}%` }}/><div className="probability-red" style={{ width: `${j.support.red}%` }}/></div>
    <p className="support-definition"><Info size={13}/><span>{j.support.definition} 支持指数不等于真实胜率，不能按概率理解。</span></p>
    {j.support.out_of_reference_range && <p className="judgment-warning">本场模型倾向超出验证参考范围；指数不提供外推准确率保证。</p>}
    <div className="judgment-summary-grid">
      <div><span><Swords size={14}/>BP 净贡献</span><b data-testid="bp-assessment">{j.bp_assessment.label}</b><small>{bpName ? `模型的 BP 项合计支持 ${bpName}` : '模型未给出可验证的 BP 净优势'}</small></div>
      <div><span><Target size={14}/>判断主要靠什么</span><b data-testid="judgment-driver">{j.driver.label}</b><small>按完整 SHAP 绝对贡献分组，非因果份额</small></div>
    </div>
    <div className="judgment-weakness" data-testid="draft-weakness"><span>本场 BP 的首要弱点</span><div><b>{j.bp_assessment.weakness.title}</b><p>{j.bp_assessment.weakness.detail}</p>{j.bp_assessment.weakness.evidence_status !== 'model' && <small>证据有限，不补造战术结论</small>}</div></div>
    <div className="judgment-evidence-grid">{mode === 'extreme' ? <>{risks}{reasons}</> : <>{reasons}{risks}</>}</div>
    <div className="judgment-reliability"><div><Database size={15}/><b>当前数据可靠性：{j.reliability.label}</b></div><ul>{j.reliability.details.map((detail, index) => <li key={index}>{detail}</li>)}</ul></div>
    <div className="judgment-model-version"><span>判断模型</span><code>{j.model_version}</code><span>方法版本 {j.version}</span></div>
  </div>
}

export function JudgmentTechnical({ judgment: j }: { judgment: AvailableJudgment }) {
  return <div className="judgment-technical" data-testid="judgment-technical">
    <h3>支持指数与判断模型的核验信息</h3>
    <p>{j.support.definition}</p>
    <dl><div><dt>验证参考样本</dt><dd>{j.support.reference_n.toLocaleString()} 局</dd></div><div><dt>判断模型校准后的蓝方概率</dt><dd>{pct(j.support.judgment_calibrated_probability)}</dd></div><div><dt>判断模型蓝方决策边距</dt><dd>{j.support.raw_margin.toFixed(4)}</dd></div><div><dt>BP 项的蓝方净贡献</dt><dd>{j.bp_assessment.net_contribution.toFixed(4)} log-odds</dd></div></dl>
    <p>{j.driver.note}</p><div className="driver-shares"><span>BP {pct(j.driver.bp_share)}</span><span>选手与战队 {pct(j.driver.players_teams_share)}</span><span>其他上下文 {pct(j.driver.context_share)}</span></div>
    <h3>真实历史胜者判断表现</h3><p>{j.evaluation.scope}</p>
    <div className="judgment-evaluation-summary"><span>全部判断 <b>{pct(j.evaluation.accuracy)}</b><small>{j.evaluation.n.toLocaleString()} 局</small></span><span>强倾向命中率 <b>{pct(j.evaluation.strong.accuracy)}</b><small>{j.evaluation.strong.n.toLocaleString()} 局 · 覆盖 {pct(j.evaluation.strong.coverage)}</small></span></div>
    <div className="table-scroll"><table className="judgment-evaluation-table"><thead><tr><th>优势等级</th><th>真实样本</th><th>命中率</th><th>覆盖率</th><th>95% Wilson 区间</th></tr></thead><tbody>{j.evaluation.grades.map(row => <tr key={row.key}><td>{row.label}</td><td>{row.n.toLocaleString()}</td><td>{pct(row.accuracy)}</td><td>{pct(row.coverage)}</td><td>{row.wilson_low === null || row.wilson_high === null ? '暂无区间' : `${pct(row.wilson_low)} – ${pct(row.wilson_high)}`}</td></tr>)}</tbody></table></div>
    <p className="tiny-copy">历史分组命中率是群体回测结果，不是本场获胜概率。三种展示模式不改变模型、支持指数或等级门槛。</p>
    <details className="judgment-evidence-details"><summary>查看本场理由的具体特征与贡献</summary><ul>{[...j.reasons, ...j.risks].map((item, index) => <li key={`${item.title}-${index}`}><b>{item.title}</b><span>蓝方原始 log-odds 贡献：{item.contribution === null ? '无已验证贡献' : item.contribution.toFixed(4)}</span><code>{item.feature_names.length ? item.feature_names.join(', ') : '未建立特征证据'}</code></li>)}</ul></details>
    <ul className="judgment-limitations">{j.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
  </div>
}
