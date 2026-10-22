"""Evidence-backed winner calls; never a replacement for calibrated probability.

All explanations are deterministic summaries of this model's *full* native
SHAP vector and real pre-cutoff observations. Unsupported tactical properties
are not inferred from champion names, lore, or hand-authored strength scores.
"""
from __future__ import annotations

from collections import defaultdict
import json
import os
from pathlib import Path
import re

import numpy as np

from .context import is_worlds_league
from .model import ModelUnavailableError, sha256

ROOT = Path(__file__).resolve().parents[2]
ROLES = {"top": "上单", "jng": "打野", "mid": "中单", "bot": "下路", "sup": "辅助"}
BP_KINDS = {"proficiency", "patch", "matchup", "mid_jungle", "bot_lane", "synergy", "picks", "bans"}


def _category(name: str) -> tuple[str, str | None]:
    role = next((role for role in ROLES if re.search(rf"(?:^|_){role}(?:_|$)", name)), None)
    if ("mid_jungle" in name or "bot_support" in name) and "players" in name:
        return "players", None
    if "mid_jungle" in name or "jng_mid" in name or "mid_jng" in name:
        return "mid_jungle", None
    if "bot_lane" in name or "bot_sup" in name or "sup_bot" in name:
        return "bot_lane", None
    if "patch" in name:
        return "patch", role
    if "player_champion" in name or "proficiency" in name:
        return "proficiency", role
    if "matchup" in name:
        return "matchup", role
    if "synergy" in name or "pair" in name:
        return "synergy", None
    if "champion" in name:
        return "picks", role
    if "ban" in name:
        return "bans", None
    if "player" in name:
        return "players", role
    if "team" in name or "roster" in name or "head_to_head" in name:
        return "teams", None
    return "context", None


def group_contributions(contributions: list[dict]) -> list[dict]:
    """Partition every feature exactly once; preserve signed and absolute sums."""
    groups: dict[tuple, dict] = {}
    for item in contributions:
        contribution = float(item["contribution"])
        if not np.isfinite(contribution):
            raise ValueError("Non-finite feature attribution")
        key = _category(item["feature"])
        group = groups.setdefault(key, {"category": key[0], "role": key[1], "contribution": 0.0,
                                       "absolute_contribution": 0.0, "features": []})
        group["contribution"] += contribution
        group["absolute_contribution"] += abs(contribution)
        group["features"].append(item)
    return list(groups.values())


def _observations(group: dict, result: dict, winner: str) -> tuple[str, int | None]:
    category, role = group["category"], group["role"]
    players = [p for p in result["players"] if role is None or p["role"] == role]
    focus = [p for p in players if p["side"] == winner]
    if category in {"proficiency", "picks"}:
        selected = players if role else sorted(players, key=lambda p: p["games"])[:2]
        parts = [f'{"蓝方" if p["side"] == "blue" else "红方"} {p["name"]} 的 {p["champion"]}：{p["games"]} 局' +
                 (f'、{p["wins"]} 胜' if p["games"] else "、没有已知赛果") for p in selected]
        return "；".join(parts), min((p["games"] for p in selected), default=0)
    if category == "players":
        selected = players if role else focus
        parts = [f'{p["name"]}：{p["player_history_games"]} 局职业历史' +
                 (f'，最近至多20局胜率 {p["player_recent_win_rate"]:.1%}'
                  if p["player_recent_win_rate"] is not None else "，近期记录缺失") for p in selected]
        return "；".join(parts), min((p["player_history_games"] for p in selected), default=0)
    if category == "matchup":
        selected = [m for m in result["matchups"] if role is None or m["role"] == role]
        parts = [f'{ROLES[m["role"]]} {m["blue_champion"]} / {m["red_champion"]}：{m["games"]} 局对位阵容样本'
                 for m in selected[:2]]
        return "；".join(parts), min((m["games"] for m in selected), default=0)
    if category in {"mid_jungle", "bot_lane", "synergy"}:
        pair = {"jng", "mid"} if category == "mid_jungle" else {"bot", "sup"} if category == "bot_lane" else None
        selected = [s for s in result["synergies"] if pair is None or set(s["roles"]) == pair]
        selected = sorted(selected, key=lambda p: p["games"])[:2]
        parts = [f'{"蓝方" if s["side"] == "blue" else "红方"} {" + ".join(s["champions"])}：{s["games"]} 局组合样本' for s in selected]
        return "；".join(parts), min((s["games"] for s in selected), default=0)
    coverage = result["prediction"]["sample_coverage"]
    if category == "patch":
        counts = [int(f["value"]) for f in group["features"] if f["feature"].endswith("_games") and isinstance(f["value"], (int, float))]
        sample = min(counts) if counts else coverage["patch_history_games"]
        return (f'当前版本共 {coverage["patch_history_games"]} 局赛前历史，本组最少的具体版本组合只有 {sample} 局；新版本类别本身不证明模型学会了该版本', sample)
    if category == "bans":
        return f'本局 {10-coverage["missing_ban_slots"]}/10 个禁用位已知；贡献来自训练中的禁用类别', None
    if category == "teams":
        return "贡献来自战队身份、截至赛前的胜负记录和已观测阵容；不等同于个人实力的因果估计", None
    return "联赛、先选权或历史总体分布等背景特征；不能将其写成英雄战术优势", None


def _evidence(group: dict, result: dict, winner: str, *, risk: bool = False) -> dict:
    titles = {"proficiency": "英雄熟练度", "patch": "版本历史", "matchup": "英雄对位",
              "mid_jungle": "中野组合", "bot_lane": "下路组合", "synergy": "阵容组合",
              "picks": "英雄选择", "bans": "禁用信息", "players": "选手身份与近期状态",
              "teams": "战队与阵容历史", "context": "比赛背景"}
    category = group["category"]
    label = (ROLES[group["role"]] + " · " if group["role"] else "") + titles[category]
    observation, sample = _observations(group, result, winner)
    side_label = "蓝方" if winner == "blue" else "红方"
    aligned = group["contribution"] * (1 if winner == "blue" else -1)
    direction = f"支持{side_label}" if aligned > 0 else f"反对{side_label}" if aligned < 0 else "净贡献为零"
    status = "limited" if sample is not None and sample < 20 else "model"
    detail = (f'本组模型贡献{direction}（蓝方原始对数胜算 {group["contribution"]:+.3f}）。{observation}。'
              + ("这一项是对手扳回局面的主要模型证据；它没有给出实际比赛中的触发概率。" if risk else
                 "这是该模型的判断依据，不是独立验证的战术因果关系。"))
    if status == "limited":
        detail += "历史样本不足，不能把这一贡献当作可靠战术定论。"
    return {"title": label + ("是反向证据" if risk else "推动本次判断"), "detail": detail,
            "category": category, "contribution": group["contribution"],
            "feature_names": [f["feature"] for f in sorted(group["features"], key=lambda f: abs(f["contribution"]), reverse=True)],
            "sample_games": sample, "evidence_status": status}


def _gap(title: str, detail: str) -> dict:
    return {"title": title, "detail": detail, "category": "evidence_gap", "contribution": None,
            "feature_names": [], "sample_games": None, "evidence_status": "unavailable"}


def reliability(result: dict, source: dict, decision: dict) -> dict:
    coverage = result["prediction"]["sample_coverage"]
    unknown = sum(len(coverage[key]) for key in ("unknown_teams", "unknown_players_in_role", "unknown_champions_in_role"))
    sparse = sum(p["games"] < 20 for p in result["players"])
    details = [f'历史覆盖 {coverage["history_games"]} 局；同版本 {coverage["patch_history_games"]} 局；{sparse}/10 个选手英雄组合少于20局。',
               "职业身份仍含未人工核验的名称关联；出场记录不等于已确认首发。"]
    low = unknown > 0 or coverage["patch_history_games"] < 100 or sparse >= 5
    if unknown:
        details.append(f"本次有 {unknown} 项战队/选手位置/英雄位置没有历史覆盖。")
    if coverage["missing_ban_slots"]:
        details.append(f'{coverage["missing_ban_slots"]} 个 ban 位未知。')
    if decision["out_of_reference_range"]:
        low = True
        details.append("模型分差超出验证期观测范围；支持指数已封顶，不能外推成更高命中率。")
    if is_worlds_league(result["prediction"].get("model_league", "")):
        low = True
        details.append(f'目标世界赛回测只有 {result["evaluation"]["worlds_target"]["n"]} 局，不能证明该赛事的稳定命中率。')
    if source.get("engine") == "frozen":
        details.append("本次使用原模型判断；增强候选没有满足部署条件或未配置使用。")
    return {"level": "low" if low else "medium", "label": "数据可靠性有限" if low else "历史覆盖中等",
            "details": details}


def explain_judgment(result: dict, contributions: list[dict], base_value: float, decision: dict, source: dict) -> dict:
    """Pure explanation builder; receives real predictions, never predicts itself."""
    winner = decision["winner_side"]
    sign = 1 if winner == "blue" else -1
    groups = group_contributions(contributions)
    positive = sorted((g for g in groups if sign*g["contribution"] > 1e-10), key=lambda g: sign*g["contribution"], reverse=True)
    negative = sorted((g for g in groups if sign*g["contribution"] < -1e-10), key=lambda g: sign*g["contribution"])
    reasons = [_evidence(g, result, winner) for g in positive[:3]]
    while len(reasons) < 3:
        reasons.append(_gap(f"第{len(reasons)+1}项独立优势尚无证据", "剩余特征没有对预测胜者形成正向净贡献；不补写阵容优势。"))
    risks = [_evidence(g, result, winner, risk=True) for g in negative[:2]]
    while len(risks) < 2:
        if not risks:
            risks.append(_gap("未被模型观测的临场执行", "模型未观测当局沟通、操作失误与临场战术；这些变化能使赛果偏离判断，不能量化成爆冷概率。"))
        else:
            risks.append(_gap("历史规律在本局失效", "版本变化、阵容变动和稀有选手英雄组合会削弱历史关系；模型没有第二项可验证的反向贡献，不补造具体爆冷触发条件。"))
    bp = [g for g in groups if g["category"] in BP_KINDS]
    bp_net = float(sum(g["contribution"] for g in bp))
    worst = min(bp, key=lambda g: sign*g["contribution"], default=None)
    weakness = (_evidence(worst, result, winner, risk=True) if worst and sign*worst["contribution"] < -1e-10 else
                _gap("没有可识别的 BP 反向证据", "模型没有给出独立的负向 BP 净贡献；这不代表阵容没有弱点。开团、控制、前后期曲线未验证，不能凭英雄名补写。"))
    masses = defaultdict(float)
    for group in groups:
        driver = "bp" if group["category"] in BP_KINDS else "players_teams" if group["category"] in {"players", "teams"} else "context"
        masses[driver] += group["absolute_contribution"]
    denominator = sum(masses.values())
    shares = {key: masses[key]/denominator if denominator else 0.0 for key in ("bp", "players_teams", "context")}
    primary = max(shares, key=shares.get) if denominator else "context"
    labels = {"bp": "主要靠 BP 与版本特征", "players_teams": "主要靠选手和战队历史", "context": "主要靠比赛背景特征"}
    bp_side = "blue" if bp_net > 1e-10 else "red" if bp_net < -1e-10 else None
    # This is a signed additive attribution, not an independently trained BP-only win model.
    bp_label = f'{"蓝方" if bp_side == "blue" else "红方"} BP 特征净占优' if bp_side else "没有可验证的 BP 净优势"
    return {"reasons": reasons, "risks": risks,
            "bp_assessment": {"favored_side": bp_side, "label": bp_label, "net_contribution": bp_net, "weakness": weakness},
            "driver": {"primary": primary, "label": labels[primary], "bp_share": shares["bp"],
                       "players_teams_share": shares["players_teams"], "context_share": shares["context"],
                       "note": f"占比为完整 SHAP 绝对贡献之和，不是胜率或因果份额；模型截距 {base_value:+.3f} 不参与占比。相关特征会分摊贡献。"},
            "reliability": reliability(result, source, decision)}


def build_judgment(payload: dict, result: dict, frozen_artifact: dict, features: dict,
                   frozen_metadata: dict, games_path: Path) -> dict:
    """Optional extension; a failed check disables it without fabricating a call."""
    try:
        from .judgment_policy import apply_policy, load_policy
        directory = Path(os.getenv("WORLDS_JUDGMENT_DIR", str(ROOT / "reports/aggressive")))
        manifest = json.loads((directory / "judgment_manifest.json").read_text())
        for filename, key in (("judgment_policy.json", "policy_sha256"), ("judgment_evaluation.json", "evaluation_sha256")):
            if sha256(directory / filename) != manifest[key]:
                raise ValueError(f"Decision artifact integrity mismatch: {filename}")
        info = json.loads((directory / "judgment_policy.json").read_text())
        engine = info["source_engine"]
        if engine == "enhanced":
            from .enhanced import predict_enhanced
            source = predict_enhanced(payload, games_path=games_path,
                                      artifact_dir=Path(os.getenv("WORLDS_ENHANCED_MODEL_DIR", str(ROOT / "models/aggressive-experiment/latest"))))
            if source.get("available") is False:
                raise ModelUnavailableError(source.get("reason", "Enhanced model is unavailable"))
            metadata = source["metadata"]
            raw = source["raw_score"]
            probability = source["calibrated_probability"]
            contributions, base = source["contributions"], source["base_value"]
        elif engine == "frozen":
            from .analysis import native_shap
            all_shap = native_shap(frozen_artifact, features, limit=len(frozen_artifact["columns"]))
            metadata, raw, probability = frozen_metadata, all_shap["raw_prediction"], result["prediction"]["blue_win_probability"]
            contributions, base = all_shap["contributions"], all_shap["base_value"]
        else:
            raise ValueError("Unknown decision model engine")
        policy = load_policy(directory / "judgment_policy.json", as_of=payload["as_of"],
                             model_version=metadata["model_version"], artifact_sha256=metadata["artifact_sha256"])
        decision = apply_policy(raw, probability, policy)
        evaluation = json.loads((directory / "judgment_evaluation.json").read_text())["deployment_test"]
        original_accuracy = result["evaluation"]["accuracy"]
        evaluation["comparison_note"] = (f'本轮实验判断回顾性测试准确率 {evaluation["accuracy"]:.2%}，'
                                         f'标准模型 {original_accuracy:.2%}；未证明整体效果提升。')
        explained = explain_judgment(result, contributions, base, decision, {"engine": engine})
        side = decision["winner_side"]
        return {"available": True, "version": "evidence-judgment-v1", "model_version": metadata["model_version"], "engine": engine,
                "winner": {"side": side, "team_id": payload[side]["team_id"], "tie_break": bool(decision["tie_break"])},
                "support": {"blue": decision["support_index"]["blue"], "red": decision["support_index"]["red"],
                            "definition": "支持指数不是获胜概率。它将模型到决策边界的距离，在验证期绝对分差中排位，再映射到两侧0–100；不保证命中率，不设置最低胜率。标准模式仍显示原始校准概率。",
                            "raw_margin": decision["margin"], "reference_n": decision["reference_n"],
                            "out_of_reference_range": decision["out_of_reference_range"],
                            "judgment_calibrated_probability": probability},
                "advantage": decision["grade"], **explained, "evaluation": evaluation,
                "limitations": ["三种展示模式使用同一判断及指数；极限模式不抬高数字，也不增加证据。",
                                evaluation["comparison_note"],
                                "优势等级描述总体模型倾向；BP 净占优另由 BP 特征的完整 SHAP 合计判断。",
                                "强倾向的历史命中率来自跨联赛回测，不能当作本场真实概率。",
                                "2026 测试集此前已经查看，本轮属于回顾性实验；需要新增未见比赛验证泛化。",
                                "中野/下路组合是历史共同出场证据；尚无经验证的开团、控制、前中后期或战队战术风格标签。",
                                "若精确落在决策边界，按固定蓝方规则给出选择并标记平局，不表示蓝方有证据优势。"]}
    except Exception as exc:
        # Fail closed for this optional layer, leaving the original API truthful.
        return {"available": False, "reason": f"激进判断不可用：{type(exc).__name__}: {exc}。标准校准预测仍然保留。"}
