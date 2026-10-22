import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDownUp, ArrowRight, Ban, Check, ChevronDown, ChevronRight, Clock3, Database, ExternalLink, History, Info, Layers3, LoaderCircle, Plus, RotateCcw, Save, Search, ShieldCheck, SlidersHorizontal, Sparkles, Swords, Trash2, Users, X } from 'lucide-react'
import { api, ApiError } from './api'
import { blockedChampions, buildRequest, championAvailability, parseApiDate, ROLES, ROLE_LABELS, ROLE_NAMES, searchChampions, sortedHistory, validateDraft } from './domain'
import type { SelectionTarget } from './domain'
import { usePredictorStore } from './store'
import type { CatalogResponse, Champion, HealthResponse, MatchSummary, PlayerLookup, Role, Side, TeamSummary } from './types'
const AnalysisPanel = lazy(() => import('./components/AnalysisPanel').then(module => ({ default: module.AnalysisPanel })))

const sideName = (side: Side) => side === 'blue' ? '蓝方' : '红方'
const shortId = (value: string) => value.length > 21 ? `${value.slice(0, 13)}…${value.slice(-5)}` : value
const time = (value: string | null | undefined) => value ? parseApiDate(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '未知'
const localDateTime = (iso: string) => { const d = new Date(iso); return Number.isNaN(d.valueOf()) ? '' : new Date(d.valueOf() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
const toISO = (value: string) => new Date(value).toISOString()

function TeamBadge({ team, name, side, small = false }: { team?: TeamSummary; name: string; side?: Side; small?: boolean }) {
  return <span className={`team-badge ${side || ''} ${small ? 'small' : ''}`} title={team?.logo_url ? '来源已记录的队徽' : '缩写标识 · 不代表官方队徽'}>{team?.logo_url ? <img src={team.logo_url} alt={`${name}队徽`}/> : <span>{team?.code || name.split(' ').map(part => part[0]).join('').slice(0, 3) || '—'}</span>}</span>
}

export default function App() {
  const state = usePredictorStore()
  const [tab, setTab] = useState<'draft' | 'matches' | 'history'>('draft')
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null)
  const [teams, setTeams] = useState<TeamSummary[]>([])
  const [teamNotice, setTeamNotice] = useState('')
  const [matches, setMatches] = useState<MatchSummary[]>([])
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [teamPicker, setTeamPicker] = useState<Side | null>(null)
  const [teamQuery, setTeamQuery] = useState('')
  const [teamBusy, setTeamBusy] = useState<Record<Side, boolean>>({ blue: false, red: false })
  const teamRequest = useRef<Record<Side, number>>({ blue: 0, red: 0 })
  const [playerPicker, setPlayerPicker] = useState<{ side: Side; role: Role } | null>(null)
  const [playerQuery, setPlayerQuery] = useState('')
  const [playerResults, setPlayerResults] = useState<PlayerLookup[]>([])
  const [playerBusy, setPlayerBusy] = useState(false)
  const [active, setActive] = useState<SelectionTarget>({ side: 'blue', role: 'top' })
  const [championQuery, setChampionQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState<Role | 'all'>('all')
  const [availableOnly, setAvailableOnly] = useState(false)
  const [matchQuery, setMatchQuery] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const [priorOpen, setPriorOpen] = useState(false)
  const [priorSelection, setPriorSelection] = useState<string[]>([])
  const [priorSearch, setPriorSearch] = useState('')
  const pickerRef = useRef<HTMLElement | null>(null)
  const champions = catalog?.champions || []
  const getChampion = (name: string) => champions.find(hero => hero.name_en === name || hero.id === name)
  const ruleAvailable = catalog?.worlds.rules.verified === true && state.settings.worlds_only && new Date(state.settings.scheduled_start).getUTCFullYear() === 2026
  const validErrors = validateDraft(state, ruleAvailable)
  const selectedCount = [...state.blue.players, ...state.red.players].filter(player => player.champion).length
  const selectedBans = [...state.blue.bans, ...state.red.bans].filter(Boolean).length
  const blocked = blockedChampions(state.series)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const timer = setTimeout(() => {
      Promise.all([api.health(), api.catalog(state.settings.as_of), api.teams(state.settings.as_of, state.settings.worlds_only), api.matches(state.settings.as_of, true)])
        .then(([h, c, t, m]) => { if (!cancelled) { setHealth(h); setCatalog(c); setTeams(t.teams); setTeamNotice(typeof t.notice === 'string' ? t.notice : ''); setMatches(m.matches); setError('') } })
        .catch((err: unknown) => { if (!cancelled) { setError(err instanceof Error ? err.message : '数据加载失败'); setHealth(null) } })
        .finally(() => { if (!cancelled) setLoading(false) })
    }, 150)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [state.settings.as_of, state.settings.worlds_only, refresh])

  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(''), 4200); return () => clearTimeout(timer) }, [notice])
  useEffect(() => { setError('') }, [state.inputRevision])
  useEffect(() => {
    if (!playerPicker) return
    let cancelled = false
    setPlayerBusy(true)
    const timer = setTimeout(() => { api.players(playerQuery, state.settings.as_of).then(response => { if (!cancelled) setPlayerResults(response.players) }).catch((err: unknown) => { if (!cancelled) setError(err instanceof Error ? err.message : '选手查询失败') }).finally(() => { if (!cancelled) setPlayerBusy(false) }) }, 220)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [playerQuery, playerPicker, state.settings.as_of])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') { setPlayerPicker(null); setSourcesOpen(false); setPriorOpen(false); setTeamPicker(null); setConfirmClear(false) } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const filteredChampions = useMemo(() => searchChampions(champions, championQuery, roleFilter).filter(hero => !availableOnly || !championAvailability(hero.name_en, state, active)), [champions, championQuery, roleFilter, availableOnly, state.blue, state.red, state.series, active])
  const filteredTeams = teams.filter(team => `${team.name} ${team.code} ${team.region}`.toLowerCase().includes(teamQuery.toLowerCase()))
  const filteredMatches = matches.filter(match => `${match.blue_team_name} ${match.red_team_name} ${match.game_id}`.toLowerCase().includes(matchQuery.toLowerCase()))

  async function chooseTeam(side: Side, team: TeamSummary) {
    const requestId = ++teamRequest.current[side]
    const sideSnapshot = usePredictorStore.getState()[side]
    const asOf = state.settings.as_of
    setTeamPicker(null); setTeamBusy(current => ({ ...current, [side]: true })); setError('')
    try {
      const roster = await api.roster(team.team_id, asOf)
      if (requestId === teamRequest.current[side] && usePredictorStore.getState().settings.as_of === asOf && usePredictorStore.getState()[side] === sideSnapshot) {
        state.setTeam(side, team, roster)
        setNotice(`${team.name} 的最近实际出场阵容已载入，请核对首发。`)
      }
    } catch (err) { setError(err instanceof Error ? err.message : '阵容加载失败，请手动选择选手。') }
    finally { if (requestId === teamRequest.current[side]) setTeamBusy(current => ({ ...current, [side]: false })) }
  }

  function chooseChampion(hero: Champion) {
    const reason = championAvailability(hero.name_en, state, active)
    if (reason) { setNotice(reason); return }
    if (active.banIndex != null) state.setBan(active.side, active.banIndex, hero.name_en)
    else if (active.role) {
      const changed = state.setChampion(active.side, active.role, hero.name_en)
      if (changed) {
        const current = usePredictorStore.getState()
        const next = (['blue', 'red'] as Side[]).flatMap(side => current[side].players.map(player => ({ side, ...player }))).find(player => !player.champion)
        if (next) setActive({ side: next.side, role: next.role })
      }
    }
  }

  async function predict() {
    const now = usePredictorStore.getState()
    const errors = validateDraft(now, ruleAvailable)
    if (errors.length) { setError(errors[0] || '请完善阵容'); return }
    if (!health?.model.available) { setError('模型不可用，无法执行真实预测。'); return }
    setBusy(true); setError(''); state.setResult(null)
    const revision = usePredictorStore.getState().inputRevision
    try {
      const result = await api.analyze(buildRequest(now))
      if (!state.setResult(result, revision)) setNotice('输入已改变，已丢弃过期响应，请重新预测。')
      else setTimeout(() => document.querySelector('[data-testid="analysis-result"]')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80)
    } catch (err) {
      setError(err instanceof Error ? err.message : '预测失败，没有生成胜率。')
      if (err instanceof ApiError && err.status === 503) setHealth(previous => previous ? { ...previous, model: { available: false, reason: err.message } } : previous)
    } finally { setBusy(false) }
  }

  function loadMatch(match: MatchSummary) {
    state.loadRequest(match.request, `${match.blue_team_name} vs ${match.red_team_name}`, {
      blue_team_name: match.blue_team_name, red_team_name: match.red_team_name, player_names: match.player_names,
    })
    setTab('draft'); setActive({ side: 'blue', role: 'top' }); setNotice('已载入真实比赛 BP；请求时点位于该局开始前，赛果不送入模型。')
  }

  const teamPanel = (side: Side) => {
    const team = state[side]
    const info = teams.find(item => item.team_id === team.team_id)
    return <section className={`team-panel panel ${side}`} aria-label={`${sideName(side)}阵容`}>
      <div className="team-side-line"><span><i className={`side-dot ${side}`}/>{side === 'blue' ? 'BLUE SIDE' : 'RED SIDE'}</span><span>{state.settings.first_pick_side === side ? 'BP 先选' : '地图选边'}</span></div>
      <button className="team-selector" aria-label={`选择${sideName(side)}战队`} aria-expanded={teamPicker === side} onClick={() => { setTeamPicker(teamPicker === side ? null : side); setTeamQuery('') }}><TeamBadge name={team.team_name} team={info} side={side}/><span><strong>{team.team_name || `选择${sideName(side)}战队`}</strong><small>{team.team_name ? `${info?.region || '真实职业战队'} · ${info?.code || 'PRO TEAM'}` : '搜索真实参赛战队'}</small></span>{teamBusy[side] ? <LoaderCircle className="spin" size={16}/> : <ChevronDown size={16}/>}</button>
      {teamPicker === side && <div className="team-dropdown"><div className="search-field"><Search size={15}/><input autoFocus aria-label={`${sideName(side)}战队搜索`} placeholder="名称 / 缩写 / 赛区" value={teamQuery} onChange={event => setTeamQuery(event.target.value)}/></div><div className="team-options">{filteredTeams.map(option => <button key={option.team_id} onClick={() => void chooseTeam(side, option)} disabled={state[side === 'blue' ? 'red' : 'blue'].team_id === option.team_id} data-testid={`team-option-${side}-${option.code}`}><TeamBadge team={option} name={option.name} small/><span><b>{option.name}</b><small>{option.region} · {option.participation_status === 'official_confirmed' ? '官方参赛名单' : '来源已记录'}</small></span>{option.team_id === team.team_id && <Check size={14}/>}</button>)}{!filteredTeams.length && <p className="empty-mini">{teamNotice || '未找到匹配战队'}</p>}</div></div>}
      <p className="roster-note" title={team.roster_notice || '选队后加载带观测日期的历史阵容'}><Info size={12}/>{team.roster_observed_at ? `实际出场记录 ${time(team.roster_observed_at)} · 首发请核对` : team.roster_notice ? '信息时点已改变，请重新加载或确认选手' : '选择战队后自动载入选手'}</p>
      <div className="player-slots">{team.players.map(player => { const hero = getChampion(player.champion); const isActive = active.side === side && active.role === player.role; return <div key={player.role} className={`player-slot ${isActive ? 'selected' : ''}`} data-testid={`${side}-${player.role}-slot`}>
        <button className="slot-portrait" aria-label={`${sideName(side)}${ROLE_NAMES[player.role]}选择英雄`} onClick={() => { setActive({ side, role: player.role }); setRoleFilter('all'); if (window.innerWidth < 760) pickerRef.current?.scrollIntoView({ behavior: 'smooth' }) }}>{hero ? <img src={hero.image_url} alt={hero.name_zh}/> : <Plus size={20}/>}<span>{ROLE_LABELS[player.role]}</span></button>
        <div className="slot-info"><button className="player-name" aria-label={`修改${sideName(side)}${ROLE_NAMES[player.role]}选手`} onClick={() => { setPlayerPicker({ side, role: player.role }); setPlayerQuery(player.name || '') }}>{player.name || '选择选手'}<ChevronDown size={11}/></button><button className="champion-name" onClick={() => setActive({ side, role: player.role })}>{hero?.name_zh || player.champion || '选择英雄'}</button><small title={player.player_id}>{player.history_games != null ? `${player.history_games} 场职业记录` : player.player_id ? shortId(player.player_id) : ROLE_NAMES[player.role]}{player.recent_win_rate != null && ` · 近期 ${(player.recent_win_rate * 100).toFixed(0)}%`}</small>{!!player.best_champions?.length && <span className="favorite-heroes" title={player.best_champions.map(item => `${getChampion(item.champion)?.name_zh || item.champion}：${item.games} 场，胜率 ${item.win_rate == null ? '未知' : (item.win_rate * 100).toFixed(1) + '%'}`).join('；')}>常用 {player.best_champions.slice(0, 3).map(item => <span key={item.champion}>{getChampion(item.champion) && <img src={getChampion(item.champion)?.image_url} alt={getChampion(item.champion)?.name_zh || item.champion}/>}</span>)}</span>}</div>
        {player.champion ? <button className="icon-button slot-clear" aria-label={`清除${sideName(side)}${ROLE_NAMES[player.role]}英雄`} onClick={() => state.setChampion(side, player.role, '')}><X size={13}/></button> : <span className="slot-order">{ROLES.indexOf(player.role) + 1}</span>}
      </div> })}</div>
      <div className="ban-heading"><span><Ban size={12}/>禁用英雄</span><small>未知可留空</small></div><div className="ban-slots">{team.bans.map((ban, index) => { const hero = ban ? getChampion(ban) : null; return <div key={index} className={`ban-slot ${active.side === side && active.banIndex === index ? 'active' : ''}`}><button aria-label={`${sideName(side)}禁用${index + 1}`} onClick={() => { setActive({ side, banIndex: index }); setRoleFilter('all') }}>{hero ? <img src={hero.image_url} alt={`禁用 ${hero.name_zh}`}/> : <Ban size={15}/>}<span>{index + 1}</span></button>{ban && <button className="ban-clear" aria-label={`清除${sideName(side)}禁用${index + 1}`} onClick={() => state.setBan(side, index, null)}><X size={10}/></button>}</div> })}</div>
    </section>
  }

  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="#" onClick={event => { event.preventDefault(); setTab('draft') }}><span className="brand-icon"><Swords size={24}/></span><span>WORLDS <b>2026</b><small>BP PREDICTOR</small></span></a><nav aria-label="主导航"><button className={tab === 'draft' ? 'active' : ''} onClick={() => setTab('draft')}><Layers3 size={15}/>BP 工作台</button><button className={tab === 'matches' ? 'active' : ''} onClick={() => setTab('matches')}><Swords size={15}/>真实比赛<span>{matches.length}</span></button><button className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}><History size={15}/>预测历史<span>{state.history.length}</span></button></nav><button className={`model-status ${health?.model.available ? 'ready' : 'offline'}`} onClick={() => setRefresh(value => value + 1)} title={health?.model.reason || health?.model.model_version}><i/>{loading ? '连接数据服务' : health?.model.available ? '真实模型已就绪' : '模型不可用'}<RotateCcw size={12}/></button></header>
    <main>
      <div className="workspace-heading"><div><div className="eyebrow"><span className="gold-line"/>WORLD CHAMPIONSHIP · 2026</div><h1>{tab === 'draft' ? <>每一次选择，<em>都有数据可循。</em></> : tab === 'matches' ? <>真实赛场，<em>回到 BP 的那一刻。</em></> : <>保留判断，<em>也保留它的依据。</em></>}</h1><p>{tab === 'draft' ? '以真实职业比赛为基础，探索阵容背后的获胜概率。' : tab === 'matches' ? '实际出场、真实 BP 与来源赛果。载入后执行严格赛前重放。' : '预测与阵容仅保存在当前浏览器，旧结果保留原始模型版本。'}</p></div><button className="button subtle" onClick={() => setSourcesOpen(true)}><Database size={15}/>数据与模型说明<ExternalLink size={12}/></button></div>
      {error && <div className="error-banner" role="alert"><Info size={17}/><span>{error}</span><button aria-label="关闭错误" onClick={() => setError('')}><X size={16}/></button></div>}
      {state.storageWarning && <div className="error-banner" role="alert"><Info size={17}/><span>{state.storageWarning}</span></div>}
      {catalog && <div className="data-ribbon"><span><Database size={11}/>当前时点可用历史 <b>{typeof catalog.provenance.history_games === 'number' ? catalog.provenance.history_games.toLocaleString() : '—'}</b> 局</span><span>数据截止 {typeof catalog.provenance.history_cutoff === 'string' ? time(catalog.provenance.history_cutoff) : '未知'}（本地时间）</span><span>来源：ChainCC · 版本与样本范围透明可查</span></div>}
      {!loading && health && !health.model.available && <div className="model-unavailable" role="status"><ShieldCheck size={18}/><div><b>真实模型当前不可用</b><p>{health.model.reason} · 可以继续编辑 BP，系统不会生成替代胜率。</p></div><button className="button subtle" onClick={() => setRefresh(value => value + 1)}>重新连接</button></div>}
      {tab === 'draft' && <>
        <div className="control-bar panel"><div className="control-field mode"><span>赛事模式</span><select aria-label="赛事模式" value={state.settings.worlds_only ? 'worlds' : 'custom'} onChange={event => { state.setSettings({ worlds_only: event.target.value === 'worlds', league: event.target.value === 'worlds' ? 'Worlds' : 'Custom' }); if (event.target.value !== 'worlds') state.setSeries({ enabled: false }) }}><option value="worlds">Worlds 2026</option><option value="custom">全部职业战队 / 自定义</option></select></div><div className="control-field patch"><span>比赛版本</span><input aria-label="比赛版本" value={state.settings.patch} onChange={event => state.setSettings({ patch: event.target.value })}/></div><div className="control-field"><span>BP 先选权</span><select aria-label="BP先选权" value={state.settings.first_pick_side} onChange={event => state.setSettings({ first_pick_side: event.target.value as 'blue' | 'red' | 'unknown' })}><option value="unknown">未知 / 未设置</option><option value="blue">蓝方先选</option><option value="red">红方先选</option></select></div><div className="control-field"><span>赛制上下文</span><select aria-label="系列赛格式" value={state.series.format} onChange={event => state.setSeries({ format: event.target.value as 'bo1' | 'bo3' | 'bo5', enabled: event.target.value === 'bo1' ? false : state.series.enabled })}><option value="bo1">单局 / Bo1</option><option value="bo3">Bo3</option><option value="bo5">Bo5</option></select></div><button className={`button settings-button ${settingsOpen ? 'active' : ''}`} onClick={() => setSettingsOpen(!settingsOpen)} aria-expanded={settingsOpen}><SlidersHorizontal size={15}/>赛前时间设置<ChevronDown size={13}/></button></div>
        {settingsOpen && <div className="advanced-settings panel"><label>比赛名称<input aria-label="比赛名称" value={state.settings.match_name} onChange={event => state.setSettings({ match_name: event.target.value })}/></label><label>信息截止时间 as_of<input type="datetime-local" aria-label="信息截止时间" value={localDateTime(state.settings.as_of)} onChange={event => { if (event.target.value) state.setSettings({ as_of: toISO(event.target.value) }) }}/></label><label>比赛开始时间<input type="datetime-local" aria-label="比赛开始时间" value={localDateTime(state.settings.scheduled_start)} onChange={event => { if (event.target.value) state.setSettings({ scheduled_start: toISO(event.target.value) }) }}/></label>{!state.settings.worlds_only && <label>联赛名称<input aria-label="联赛名称" value={state.settings.league} onChange={event => state.setSettings({ league: event.target.value })}/></label>}<p>使用本地时区显示。仅使用信息截止时间前已知的赛果；完整 BP 应在该时点已知。</p></div>}
        <div className="draft-board">{teamPanel('blue')}<div className="draft-center"><div className="stage-label">DRAFT ROOM</div><div className="vs-emblem"><span>VS</span><Swords size={25}/></div><p className="board-caption">地图蓝红方与 BP 先选权<br/>分别设置，独立建模</p><button className="swap-button" onClick={() => { state.swapSides(); setNotice('双方阵容已交换，先选权随原战队移动。') }} aria-label="交换蓝红方"><ArrowDownUp size={16}/>交换双方</button><div className="draft-progress"><div><span>阵容完成度</span><b>{selectedCount}<small>/10</small></b></div><div className="completion-dots">{Array.from({ length: 10 }, (_, index) => <i key={index} className={index < selectedCount ? index < 5 ? 'blue' : 'red' : ''}/>)}</div><small>{selectedBans} 个禁用 · {blocked.length} 个 Fearless 排除</small></div><button className="predict-button" onClick={() => void predict()} disabled={busy || loading || !health?.model.available || validErrors.length > 0} data-testid="predict-button">{busy ? <LoaderCircle size={18} className="spin"/> : <Sparkles size={18}/>}<span>{busy ? '真实模型计算中' : '开始预测'}</span>{!busy && <ArrowRight size={17}/>}</button><p className="validation-hint">{busy ? '读取赛前历史，计算概率与特征贡献…' : validErrors[0] || '阵容已就绪 · 不含当前局赛后数据'}</p><div className="draft-actions"><button onClick={() => { state.saveDraft(); setNotice('当前阵容已保存到本机。') }}><Save size={13}/>保存阵容</button><button onClick={() => { state.clearBP(); setActive({ side: 'blue', role: 'top' }) }}><RotateCcw size={13}/>清空 BP</button></div><button className="text-button reset-heroes" onClick={() => state.resetChampions()}>仅重置所选英雄</button>{matches[0] && <button className="load-real-match" onClick={() => matches[0] && loadMatch(matches[0])}>载入一场真实 BP<ChevronRight size={14}/></button>}</div>{teamPanel('red')}</div>
        {state.series.format !== 'bo1' && <section className="fearless-panel panel"><div><div className="card-heading"><h3><ShieldCheck size={16}/>Fearless Draft 上下文</h3><label className="toggle-label"><input type="checkbox" checked={state.series.enabled} disabled={!ruleAvailable} onChange={event => state.setSeries({ enabled: event.target.checked })}/>启用 Worlds 已核验规则</label></div><p>{catalog?.worlds.rules.description || '官方规则正在核验；未核验前不启用限制。'} 当前只限制后续小局英雄，不预测系列赛胜率。</p></div>{state.series.enabled && <><div className="prior-games">{state.series.previous_games.map((game, index) => <div key={index} className="prior-game"><b>GAME {index + 1}</b><span>{[...game.blue_champions, ...game.red_champions].map(name => getChampion(name)?.name_zh || name).join(' · ')}</span><button aria-label={`删除前序小局${index + 1}`} onClick={() => state.setSeries({ previous_games: state.series.previous_games.filter((_, i) => i !== index) })}><X size={13}/></button></div>)}</div><button className="button subtle" onClick={() => { setPriorSelection([]); setPriorSearch(''); setPriorOpen(true) }} disabled={state.series.previous_games.length >= (state.series.format === 'bo3' ? 2 : 4)}><Plus size={14}/>记录前序小局英雄</button></>}</section>}
        <section className="champion-panel panel" ref={pickerRef}><div className="champion-toolbar"><div><p className="eyebrow">CHAMPION POOL</p><h2>选择英雄 <span className={`selection-target ${active.side}`}>{sideName(active.side)} · {active.role ? ROLE_NAMES[active.role] : `禁用 ${(active.banIndex || 0) + 1}`}</span></h2></div><div className="search-field champion-search"><Search size={17}/><input aria-label="英雄搜索" placeholder="搜索英雄名称、中英文或称号…" value={championQuery} onChange={event => setChampionQuery(event.target.value)}/>{championQuery && <button aria-label="清空英雄搜索" onClick={() => setChampionQuery('')}><X size={14}/></button>}</div></div><div className="champion-filters"><div className="role-filters"><button className={roleFilter === 'all' ? 'active' : ''} onClick={() => setRoleFilter('all')}>全部英雄</button>{ROLES.map(role => <button key={role} className={roleFilter === role ? 'active' : ''} onClick={() => setRoleFilter(role)}>{ROLE_LABELS[role]}</button>)}</div><label><input type="checkbox" checked={availableOnly} onChange={event => setAvailableOnly(event.target.checked)}/>仅显示可选</label><small>{filteredChampions.length} 位英雄</small></div>{loading && !champions.length ? <div className="loading-state"><LoaderCircle className="spin"/>正在加载官方英雄资料…</div> : <div className="champion-grid">{filteredChampions.map(hero => { const reason = championAvailability(hero.name_en, state, active); const current = active.role ? state[active.side].players.find(p => p.role === active.role)?.champion : state[active.side].bans[active.banIndex || 0]; const isCurrent = current === hero.name_en; return <button key={hero.id} className={`champion-card ${reason ? 'unavailable' : ''} ${isCurrent ? `chosen ${active.side}` : ''}`} disabled={!!reason} title={reason || `${hero.name_zh} · ${hero.name_en}`} onClick={() => chooseChampion(hero)} data-testid={`champion-${hero.id}`}><div><img loading="lazy" src={hero.image_url} alt={hero.name_zh}/>{isCurrent && <span className="pick-check"><Check size={13}/></span>}{reason && <span className="unavailable-label">{reason.includes('Fearless') ? '已使用' : reason.includes('禁用') ? '已禁用' : '已选择'}</span>}</div><b>{hero.name_zh}</b><small>{hero.name_en}</small></button> })}{!filteredChampions.length && <div className="empty-search"><Search size={24}/><p>没有匹配的英雄</p><button className="text-button" onClick={() => { setChampionQuery(''); setRoleFilter('all'); setAvailableOnly(false) }}>重置筛选</button></div>}</div>}<div className="pool-footnote"><span>英雄资料与头像：Riot Data Dragon 16.20.1</span><span>位置筛选基于历史职业出场，不限制自由换位。</span></div></section>
        <Suspense fallback={<div className="loading-state panel">正在加载分析面板…</div>}><AnalysisPanel result={state.result} champions={champions} blueName={state.blue.team_name} redName={state.red.team_name} saved={state.resultSource === 'saved'} onSave={() => { const id = state.saveRecord(); setNotice(id ? '预测快照已保存，后续模型升级不会改写此结果。' : '请先完成一次真实预测。') }}/></Suspense>
      </>}
      {tab === 'matches' && <section className="matches-section"><div className="section-heading"><div><h2>Worlds 2026 · 实际比赛</h2><p>来源覆盖范围内的真实对局；未收录的比赛不会被补造。</p></div><div className="search-field"><Search size={15}/><input aria-label="历史比赛搜索" placeholder="搜索战队或比赛 ID" value={matchQuery} onChange={event => setMatchQuery(event.target.value)}/></div></div><div className="matches-grid">{filteredMatches.map(match => <article className="match-card panel" key={match.game_id}><div className="match-card-meta"><span><i className="gold-dot"/>WORLDS 2026</span><span>{time(match.date)}</span></div><div className="match-card-teams"><div><TeamBadge name={match.blue_team_name} team={teams.find(t => t.team_id === match.blue_team_id)} side="blue"/><b>{match.blue_team_name}</b></div><span>VS</span><div><TeamBadge name={match.red_team_name} team={teams.find(t => t.team_id === match.red_team_id)} side="red"/><b>{match.red_team_name}</b></div></div><div className="match-outcome"><span className={match.blue_win === 1 ? 'blue-text' : 'red-text'}>来源赛果：{match.blue_win === 1 ? match.blue_team_name : match.red_team_name} 获胜</span><small>{match.patch}</small></div><button className="button subtle full" onClick={() => loadMatch(match)}>载入赛前 BP<ArrowRight size={15}/></button><small className="match-id">{match.game_id}</small></article>)}</div>{!filteredMatches.length && <div className="empty-analysis panel"><Database/><p>当前时点没有已收录的目标赛事比赛。</p></div>}</section>}
      {tab === 'history' && <section className="history-section"><div className="section-heading"><div><h2>本机预测档案 <span className="quiet-tag">{state.history.length} 条记录</span></h2><p>按比赛日期排序。保留原始概率、激进判断、模型版本与数据时点。</p></div><button className="button subtle danger" disabled={!state.history.length} onClick={() => setConfirmClear(true)}><Trash2 size={14}/>清空记录</button></div>{sortedHistory(state.history).map(record => <article className="history-card panel" key={record.id} data-testid="history-record"><div className="history-title"><div><span className="pill neutral">{record.recordType === 'prediction' ? '预测快照' : '阵容草稿'}</span><h3>{record.match_name}</h3><p><Clock3 size={12}/>{time(record.match_date)} · 保存于 {time(record.created_at)}</p></div><div className="history-probabilities">{record.result ? <><b className="blue-text">{(record.result.prediction.blue_win_probability * 100).toFixed(1)}%</b><span>/</span><b className="red-text">{(record.result.prediction.red_win_probability * 100).toFixed(1)}%</b></> : <span>尚未预测</span>}</div></div><div className="history-teams"><span>{record.snapshot.blue.team_name || '蓝方'} · {record.snapshot.blue.players.map(p => getChampion(p.champion)?.name_zh || p.champion || '—').join(' / ')}</span><span>{record.snapshot.red.team_name || '红方'} · {record.snapshot.red.players.map(p => getChampion(p.champion)?.name_zh || p.champion || '—').join(' / ')}</span></div>{record.result?.judgment?.available && <div className="history-judgment"><b>预测胜者：{record.snapshot[record.result.judgment.winner.side].team_name || sideName(record.result.judgment.winner.side)}</b><span>{record.result.judgment.advantage.label}</span><span>支持指数 {record.result.judgment.support.blue.toFixed(1)} / {record.result.judgment.support.red.toFixed(1)}</span><small>指数不是概率 · 保存当时的判断</small></div>}{record.result && <p className="history-version">{record.result.prediction.model_version} · 数据截止 {time(record.result.prediction.data_cutoff)}</p>}<div className="history-actions"><label>实际赛果<select aria-label={`实际赛果-${record.id}`} value={record.actual_result || ''} onChange={event => state.setActualResult(record.id, event.target.value ? event.target.value as Side : null, 'manual')}><option value="">未录入</option><option value="blue">蓝方获胜</option><option value="red">红方获胜</option></select></label>{record.actual_result && <small>用户手动录入 · 非来源核验标签{record.result ? ` · ${record.result.judgment?.available ? '激进判断' : '标准模型'}${(record.result.judgment?.available ? record.result.judgment.winner.side : record.result.prediction.blue_win_probability >= .5 ? 'blue' : 'red') === record.actual_result ? '命中' : '未命中'}` : ''}</small>}<div><button className="button subtle" onClick={() => { state.loadRecord(record.id); setTab('draft'); setNotice('已恢复原始快照，旧模型结果未被改写。') }}>恢复阵容<ArrowRight size={13}/></button><button className="icon-button danger" aria-label={`删除记录-${record.id}`} onClick={() => state.deleteRecord(record.id)}><Trash2 size={15}/></button></div></div></article>)}{!state.history.length && <div className="empty-history panel"><History size={32}/><h3>你的第一份判断，从这里开始。</h3><p>在 BP 工作台保存阵容，或在真实预测后保存完整快照。</p><button className="button gold-button" onClick={() => setTab('draft')}>前往 BP 工作台<ArrowRight size={14}/></button></div>}</section>}
      <footer><div className="footer-top"><span><Swords size={16}/>WORLDS 2026 BP PREDICTOR</span><button onClick={() => setSourcesOpen(true)}>数据来源与使用声明<ExternalLink size={12}/></button><span>研究与娱乐分析 · 不提供博彩或投注建议</span></div><p>Worlds 2026 BP Predictor isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games and all associated properties are trademarks or registered trademarks of Riot Games, Inc.</p><small>职业比赛数据：ChainCC（CC BY 4.0） · 英雄素材：Riot Data Dragon · 本地稳定选手标识不等同于已核验的官方人物 ID。</small></footer>
    </main>
    {notice && <div className="toast" role="status"><Check size={15}/>{notice}</div>}
    {playerPicker && <div className="modal-backdrop" onClick={() => setPlayerPicker(null)}><section className="modal player-modal" role="dialog" aria-modal="true" aria-labelledby="player-modal-title" onClick={event => event.stopPropagation()}><div className="modal-heading"><div><p className="eyebrow">PRO PLAYER REGISTRY</p><h2 id="player-modal-title">更换{sideName(playerPicker.side)}{ROLE_NAMES[playerPicker.role]}选手</h2></div><button className="icon-button" aria-label="关闭选手选择" onClick={() => setPlayerPicker(null)}><X size={18}/></button></div><p>查询当前 as_of 前已观测的职业名称及稳定 ID。改名、同名仍需核对。</p><div className="search-field"><Search size={16}/><input autoFocus aria-label="职业选手搜索" placeholder="职业比赛 ID / 选手名称" value={playerQuery} onChange={event => setPlayerQuery(event.target.value)}/></div><div className="player-results">{playerBusy ? <div className="loading-state"><LoaderCircle className="spin"/>查询真实选手注册表…</div> : playerResults.map(player => <button key={`${player.player_id}-${player.alias}`} onClick={() => { state.setPlayer(playerPicker.side, playerPicker.role, { player_id: player.player_id, name: player.alias }); setPlayerPicker(null) }}><span className="player-avatar"><Users size={19}/></span><span><b>{player.alias}</b><small>{player.player_id}</small></span><ArrowRight size={15}/></button>)}{!playerBusy && !playerResults.length && <p className="empty-mini">该时点没有匹配的职业名称。请使用已知稳定标识，不使用排位账号。</p>}</div>{/^(pro:|oe:player:|source:).+/.test(playerQuery) && <button className="button subtle full" onClick={() => { state.setPlayer(playerPicker.side, playerPicker.role, { player_id: playerQuery.trim(), name: playerQuery.trim() }); setPlayerPicker(null) }}>使用输入的职业稳定 ID（历史覆盖会另行报告）</button>}</section></div>}
    {sourcesOpen && <div className="modal-backdrop" onClick={() => setSourcesOpen(false)}><section className="modal sources-modal" role="dialog" aria-modal="true" aria-labelledby="sources-title" onClick={event => event.stopPropagation()}><div className="modal-heading"><div><p className="eyebrow">TRANSPARENT BY DESIGN</p><h2 id="sources-title">知道数据，也知道边界。</h2></div><button className="icon-button" aria-label="关闭数据说明" onClick={() => setSourcesOpen(false)}><X size={18}/></button></div><div className="source-item"><Database/><div><h3>真实职业比赛</h3><p>使用 ChainCC 原始比赛数据，按 game_id + side 连接并验证。数据版本、来源与实际截止时间在响应中保留。</p><a href="https://chaincc.lol/free/data/" target="_blank" rel="noreferrer">ChainCC · CC BY 4.0 <ExternalLink size={12}/></a></div></div><div className="source-item"><ShieldCheck/><div><h3>模型与评测</h3><p>按时间顺序训练、选择、校准与独立测试。全联赛测试 9,309 局；目标 Worlds 版本只有 22 局，不能证明可靠的赛事专项准确率。BP 前后概率差不是因果收益。</p><p className="mono">{health?.model.model_version || '当前无可用模型'}<br/>训练标签截止：{health?.model.label_cutoff || '未知'}</p></div></div><div className="source-item"><Users/><div><h3>名单与身份</h3><p>参赛资格使用官方来源。自动填充标注最近实际出场时间，不能直接当作当前首发；选手名称关联使用本地稳定注册表，尚非完整人工核验身份。</p><a href="https://lolesports.com/en-US/news/worlds-2026-primer" target="_blank" rel="noreferrer">Worlds 官方赛事说明 <ExternalLink size={12}/></a></div></div><div className="source-item"><Info/><div><h3>素材与非官方声明</h3><p>英雄中文、英文名称和头像来自 Riot Data Dragon；角色位置源于历史出场。缺少明确素材许可的队伍使用中性缩写标识。页面不使用未验证的手工英雄评分。</p><a href="https://developer.riotgames.com/policies/general" target="_blank" rel="noreferrer">Riot 开发者政策 <ExternalLink size={12}/></a></div></div></section></div>}
    {confirmClear && <div className="modal-backdrop"><section className="modal confirm-modal" role="dialog" aria-modal="true" aria-labelledby="clear-title"><Trash2 size={26}/><h2 id="clear-title">清空本机所有历史记录？</h2><p>这会删除当前浏览器中的阵容草稿与预测快照，无法撤销。</p><div><button className="button subtle" onClick={() => setConfirmClear(false)}>取消</button><button className="button danger-button" onClick={() => { state.clearHistory(); setConfirmClear(false); setNotice('本机历史记录已清空。') }}>确认清空</button></div></section></div>}
    {priorOpen && <div className="modal-backdrop"><section className="modal prior-modal" role="dialog" aria-modal="true" aria-labelledby="prior-title"><div className="modal-heading"><div><p className="eyebrow">FEARLESS CONTEXT</p><h2 id="prior-title">记录 GAME {state.series.previous_games.length + 1} 已用英雄</h2></div><button className="icon-button" aria-label="关闭前序英雄记录" onClick={() => setPriorOpen(false)}><X size={18}/></button></div><p>依次选择蓝方 5 个、红方 5 个实际使用英雄。只记录已发生的 BP；禁用英雄每局重新设置。</p><div className="prior-selection">{Array.from({ length: 10 }, (_, index) => <button className={index < 5 ? 'blue' : 'red'} key={index} onClick={() => setPriorSelection(current => current.filter((_, i) => i !== index))}>{priorSelection[index] ? getChampion(priorSelection[index] || '')?.name_zh || priorSelection[index] : `${index < 5 ? '蓝' : '红'} ${index % 5 + 1}`}</button>)}</div><div className="search-field"><Search size={15}/><input aria-label="前序英雄搜索" value={priorSearch} onChange={event => setPriorSearch(event.target.value)} placeholder="搜索前序小局的实际英雄"/></div><div className="prior-champion-grid">{searchChampions(champions, priorSearch).map(hero => <button key={hero.id} disabled={blocked.includes(hero.name_en) || priorSelection.includes(hero.name_en) || priorSelection.length >= 10} onClick={() => setPriorSelection(current => [...current, hero.name_en])}><img src={hero.image_url} alt=""/><span>{hero.name_zh}</span></button>)}</div><button className="button gold-button full" disabled={priorSelection.length !== 10} onClick={() => { state.setSeries({ previous_games: [...state.series.previous_games, { blue_champions: priorSelection.slice(0, 5), red_champions: priorSelection.slice(5) }] }); setPriorOpen(false); setNotice('前序英雄已记录；冲突的当前选择须重新调整。') }}>保存该局的 10 个英雄<Check size={15}/></button></section></div>}
  </div>
}
