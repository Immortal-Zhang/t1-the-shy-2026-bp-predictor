"""Real single-map model comparison, historical statistics and native SHAP.

This module extends presentation only. It does not alter trained features,
retrain models, or turn descriptive draft statistics into invented strengths.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations
import json
import os
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from catboost import Pool
from pydantic import BaseModel, ConfigDict, Field

from .context import is_worlds_league
from .data import load_games
from .features import ROLES, features_for_game
from .lookup import resolve_request_ids
from .model import ModelUnavailableError, _logits, predict, request_to_game, sha256
from .schemas import PredictionRequest


class PreviousDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blue_champions: list[str] = Field(min_length=5, max_length=5)
    red_champions: list[str] = Field(min_length=5, max_length=5)


class DraftContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    format: Literal["bo1", "bo3", "bo5"] = "bo1"
    previous_games: list[PreviousDraft] = Field(default_factory=list, max_length=4)


class AnalysisRequest(PredictionRequest):
    draft_context: DraftContext | None = None


def _catalog_functions():
    try:
        from .catalog import canonical_champion, get_worlds_rules
        return canonical_champion, get_worlds_rules
    except ImportError as exc:
        raise ModelUnavailableError("Verified champion catalog is unavailable") from exc


def prepare_request(payload: dict, games_path: Path) -> tuple[dict, dict]:
    """Normalize verified champion/identity aliases, then revalidate uniqueness."""
    parsed = AnalysisRequest.model_validate(payload).model_dump(mode="json")
    context = parsed.pop("draft_context", None) or {"enabled": False, "format": "bo1", "previous_games": []}
    canonical_champion, get_worlds_rules = _catalog_functions()
    try:
        for side in ("blue", "red"):
            for player in parsed[side]["players"]:
                player["champion"] = canonical_champion(player["champion"])
            parsed[side]["bans"] = [canonical_champion(champion) if champion is not None else None for champion in parsed[side]["bans"]]
        for prior in context["previous_games"]:
            for side in ("blue", "red"):
                prior[f"{side}_champions"] = [canonical_champion(champion) for champion in prior[f"{side}_champions"]]
    except (FileNotFoundError, OSError) as exc:
        raise ModelUnavailableError("Verified champion catalog files are unavailable; refresh catalog first") from exc
    registry = games_path.parent / "player_registry.csv"
    if registry.exists():
        alias = os.getenv("WORLDS_ALIASES_PATH")
        parsed = resolve_request_ids(parsed, registry, Path(alias) if alias else None)
    parsed = PredictionRequest.model_validate(parsed).model_dump(mode="json")
    validation = {"enabled": bool(context["enabled"]), "rule": None, "source_url": None,
                  "excluded_champions": [], "note": "Series context is a selection constraint only; the model predicts one map, not a series probability."}
    if context["enabled"]:
        if not is_worlds_league(parsed["league"]) or pd.Timestamp(parsed["scheduled_start"]).year != 2026:
            raise ValueError("Fearless rules are verified only for Worlds 2026; this event's applicable rules have not been verified")
        if context["format"] == "bo1":
            raise ValueError("Fearless history is only applicable to a verified Bo3 or Bo5 series")
        if len(context["previous_games"]) >= int(context["format"][-1]):
            raise ValueError("Previous-game count exceeds the selected series format")
        try:
            rules = get_worlds_rules()
        except (OSError, ValueError) as exc:
            raise ModelUnavailableError("Official Fearless rules are unavailable; no rule was assumed") from exc
        if not rules.get("verified") or rules.get("fearless_mode") not in {"global", "global_series"}:
            raise ModelUnavailableError("This event's global Fearless rules are not verified; disable context or verify official rules")
        formats = rules.get("applicable_formats", rules.get("formats", []))
        if context["format"] not in formats:
            raise ValueError("The selected series format is not covered by the verified Fearless rule")
        excluded: set[str] = set()
        for prior in context["previous_games"]:
            picks = prior["blue_champions"] + prior["red_champions"]
            if len(set(picks)) != 10:
                raise ValueError("Each previous map must contain ten distinct picked champions")
            if excluded.intersection(picks):
                raise ValueError("Previous maps already repeat a champion under the verified global Fearless rule")
            excluded.update(picks)
        current_picks = {player["champion"] for side in ("blue", "red") for player in parsed[side]["players"]}
        blocked = sorted(excluded.intersection(current_picks))
        if blocked:
            raise ValueError("Fearless Draft blocks previously picked champions: " + ", ".join(blocked))
        current_bans = {champion for side in ("blue", "red") for champion in parsed[side]["bans"] if champion is not None}
        unavailable_bans = sorted(excluded.intersection(current_bans))
        if unavailable_bans:
            raise ValueError("Fearless Draft: previously picked champions are unavailable as bans: " + ", ".join(unavailable_bans))
        validation.update(rule=rules["fearless_mode"], source_url=rules.get("source_url"), excluded_champions=sorted(excluded))
    return parsed, validation


def _load_artifacts(model_dir: Path) -> tuple[dict, dict, dict, dict]:
    """Only deserialize local artifacts after matching phase-one recorded hashes."""
    try:
        metadata = json.loads((model_dir / "metadata.json").read_text())
        run_dir = model_dir.parent / metadata["run_id"]
        evaluation = json.loads((run_dir / "evaluation.json").read_text())
        if metadata["status"] != "trained" or evaluation["status"] != "complete" or evaluation["run_id"] != metadata["run_id"]:
            raise ValueError("Invalid trained-model or evaluation state")
        if sha256(Path(__file__).with_name("features.py")) != metadata["feature_code_sha256"]:
            raise ValueError("Trained feature code changed; retraining is required")
        selected_path = model_dir / "selected_model.joblib"
        selected_name = metadata["selected_model"]
        selected_hash = sha256(selected_path)
        if selected_hash != metadata["artifact_sha256"] or selected_hash != evaluation["models"][selected_name]["artifact_sha256"]:
            raise ValueError("Selected model hash mismatch")
        baseline_path = run_dir / "B_catboost.joblib"
        if sha256(baseline_path) != evaluation["models"]["B_catboost"]["artifact_sha256"]:
            raise ValueError("Pre-BP model hash mismatch")
        selected, baseline = joblib.load(selected_path), joblib.load(baseline_path)
        if selected["level"] != "C" or selected["kind"] != "catboost" or baseline["level"] != "B":
            raise ValueError("Analysis requires the verified C CatBoost and B baseline artifacts")
        return metadata, evaluation, selected, baseline
    except Exception as exc:
        raise ModelUnavailableError(f"Real comparison models are unavailable: {exc}") from exc


def _rate(outcomes: pd.Series) -> float | None:
    return float(outcomes.mean()) if len(outcomes) else None


def _sample_status(count: int) -> str:
    return "none" if count == 0 else "limited" if count < 20 else "sufficient"


def _player_rows(history: pd.DataFrame, player_id: str, role: str, champion: str | None = None) -> pd.DataFrame:
    samples = []
    for side in ("blue", "red"):
        chosen = history[f"{side}_{role}_player_id"].eq(player_id)
        if champion is not None:
            chosen &= history[f"{side}_{role}_champion"].eq(champion)
        rows = history.loc[chosen, ["game_id", "date", "blue_win", f"{side}_{role}_player_name"]].copy()
        rows["win"] = rows.blue_win if side == "blue" else 1-rows.blue_win
        rows["name"] = rows[f"{side}_{role}_player_name"]
        samples.append(rows[["game_id", "date", "win", "name"]])
    return pd.concat(samples, ignore_index=True).sort_values(["date", "game_id"])


def historical_analysis(history: pd.DataFrame, game: dict) -> tuple[list, list, list]:
    """Descriptive real counts, explicitly separate from smoothed model features."""
    players, matchups, synergies = [], [], []
    for side in ("blue", "red"):
        for role in ROLES:
            player_id, champion = game[f"{side}_{role}_player_id"], game[f"{side}_{role}_champion"]
            chosen = _player_rows(history, player_id, role, champion)
            all_player = _player_rows(history, player_id, role)
            players.append({"side": side, "role": role, "player_id": player_id,
                            "name": str(all_player.iloc[-1]["name"]) if len(all_player) else player_id,
                            "champion": champion, "games": len(chosen), "wins": int(chosen.win.sum()),
                            "win_rate": _rate(chosen.win), "last_played": chosen.date.max().isoformat() if len(chosen) else None,
                            "recent_games": min(20, len(chosen)), "recent_win_rate": _rate(chosen.tail(20).win),
                            "player_history_games": len(all_player), "player_recent_win_rate": _rate(all_player.tail(20).win),
                            "sample_status": _sample_status(len(chosen))})
        for first, second in combinations(ROLES, 2):
            champ1, champ2 = game[f"{side}_{first}_champion"], game[f"{side}_{second}_champion"]
            outcomes = []
            for observed_side in ("blue", "red"):
                mask = history[f"{observed_side}_{first}_champion"].eq(champ1) & history[f"{observed_side}_{second}_champion"].eq(champ2)
                win = history.loc[mask, "blue_win"]
                outcomes.append(win if observed_side == "blue" else 1-win)
            wins = pd.concat(outcomes, ignore_index=True)
            synergies.append({"side": side, "champions": [champ1, champ2], "roles": [first, second], "games": len(wins), "win_rate": _rate(wins), "sample_status": _sample_status(len(wins))})
    for role in ROLES:
        blue, red = game[f"blue_{role}_champion"], game[f"red_{role}_champion"]
        forward = history[f"blue_{role}_champion"].eq(blue) & history[f"red_{role}_champion"].eq(red)
        reverse = history[f"red_{role}_champion"].eq(blue) & history[f"blue_{role}_champion"].eq(red)
        wins = pd.concat([history.loc[forward, "blue_win"], 1-history.loc[reverse, "blue_win"]], ignore_index=True)
        matchups.append({"role": role, "blue_champion": blue, "red_champion": red,
                         "games": len(wins), "blue_win_rate": _rate(wins), "sample_status": _sample_status(len(wins))})
    return players, matchups, synergies


def _feature_label(name: str) -> str:
    words = {"blue": "蓝方", "red": "红方", "top": "上单", "jng": "打野", "mid": "中单", "bot": "下路", "sup": "辅助",
             "team": "战队", "player": "选手", "champion": "英雄", "matchup": "对线", "patch": "版本", "synergy": "组合",
             "recent": "近期", "win": "胜", "rate": "率", "games": "场次", "id": "标识", "diff": "差值", "historical": "历史",
             "mean": "均值", "min": "最少", "known": "已知", "count": "数量", "game": "比赛", "league": "联赛", "first": "先", "pick": "选", "side": "方", "bans": "禁用", "pairs": "组合数"}
    return " · ".join(words.get(part, f"禁用 {part[3:]}" if part.startswith("ban") else part) for part in name.split("_"))


def native_shap(artifact: dict, features: dict, limit: int = 16) -> dict:
    x = pd.DataFrame([features])[artifact["columns"]]
    pool = Pool(x, cat_features=artifact["categorical"])
    vector = np.asarray(artifact["estimator"].get_feature_importance(pool, type="ShapValues"))[0]
    raw = float(np.asarray(artifact["estimator"].predict(pool, prediction_type="RawFormulaVal")).reshape(-1)[0])
    if not np.isfinite(vector).all() or not np.isclose(vector.sum(), raw, rtol=1e-6, atol=1e-6):
        raise ModelUnavailableError("Native SHAP reconstruction failed; no explanation was fabricated")
    ordered = np.argsort(np.abs(vector[:-1]))[::-1]
    top = ordered[:limit]
    contributions = [{"feature": artifact["columns"][int(index)], "label": _feature_label(artifact["columns"][int(index)]),
                      "value": features[artifact["columns"][int(index)]], "contribution": float(vector[index])} for index in top]
    return {"method": "CatBoost SHAP", "space": "raw_log_odds", "base_value": float(vector[-1]), "raw_prediction": raw,
            "contributions": contributions, "other_contribution": float(vector[:-1].sum()-vector[top].sum()),
            "feature_count": len(artifact["columns"]), "reconstruction_error": float(abs(vector.sum()-raw)),
            "notice": "这是模型原始蓝方对数胜算的特征贡献；正值推向蓝方，负值推向红方。显示前16项及其余项合计。最终概率另经 sigmoid 校准，SHAP 不是胜负的确定原因，也不是百分点贡献。"}


def analyze(payload: dict, model_dir: Path, games_path: Path) -> dict:
    model_dir, games_path = Path(model_dir), Path(games_path)
    normalized, draft_validation = prepare_request(deepcopy(payload), games_path)
    metadata, evaluation, selected, baseline = _load_artifacts(model_dir)
    # Phase-one prediction owns its cutoff, artifact integrity and probability checks.
    prediction = predict(normalized, model_dir=model_dir, games_path=games_path)
    history = load_games(games_path, as_of=normalized["as_of"])
    if normalized.get("game_id"):
        history = history.loc[history.game_id != normalized["game_id"]].copy()
    game = request_to_game(normalized)
    feature, _ = features_for_game(history, game, as_of=normalized["as_of"])
    x = pd.DataFrame([feature])[baseline["columns"]]
    raw_pre = baseline["estimator"].predict_proba(x)[:, 1]
    pre = float(baseline["calibrator"].predict_proba(_logits(raw_pre))[0, 1])
    if not np.isfinite(pre) or not 0 <= pre <= 1:
        raise ModelUnavailableError("Pre-BP model did not return a valid probability")
    post = prediction["blue_win_probability"]
    players, matchups, synergies = historical_analysis(history, game)
    scores = evaluation["models"][metadata["selected_model"]]
    metric_names = ("n", "accuracy", "roc_auc", "log_loss", "brier_score", "ece_10")
    summary = {key: scores["test_calibrated"].get(key) for key in metric_names}
    summary.update(worlds_target={key: scores["test_worlds_2026_target_patch"].get(key) for key in metric_names},
                   scope="冻结模型的全联赛时间顺序独立测试；Worlds 目标版本样本很少。评测指标是已保存的研究报告，未参与本次预测特征。",
                   evaluated_data_cutoff=metadata["evaluation_data_cutoff"])
    comparison = {"pre_bp": {"model": metadata["run_id"] + "/B_catboost", "blue_probability": pre, "red_probability": 1-pre},
                  "post_bp": {"model": metadata["model_version"], "blue_probability": post, "red_probability": 1-post},
                  "delta_blue": post-pre,
                  "limitation": "两个模型使用相同时间切分、同类独立 sigmoid 校准，但 B 使用近期样本权重，部署 C 使用均匀权重；C 同时加入 BP 与版本，差值不能隔离 BP 的因果效应。"}
    result = {"prediction": prediction, "comparison": comparison, "players": players, "matchups": matchups, "synergies": synergies,
            "explanation": native_shap(selected, feature), "evaluation": summary,
            "draft_context_validation": draft_validation,
            "supported_analysis": {
                "player_form": {"available": True, "kind": "model_feature_and_descriptive_history", "description": "角色内更早比赛的胜负与近期20局表现；不是独立个人实力分。"},
                "proficiency": {"available": True, "kind": "model_feature_and_descriptive_history", "description": "选手-英雄-位置的历史样本；面板给出未平滑真实计数，模型另用平滑估计。"},
                "matchups": {"available": True, "kind": "model_feature_and_descriptive_history", "description": "同位置英雄对位的早期已知胜负统计，混杂于选手/队伍水平。"},
                "synergy": {"available": True, "kind": "model_feature_and_descriptive_history", "description": "位置化两英雄同时出场的历史胜负统计，不是确定的协同强度。"},
                "patch_adaptation": {"available": True, "kind": "model_feature", "description": "版本类别及版本内英雄历史计数已参与 C 模型；样本少时收缩。"},
                "early_late_damage_engage_protection_cc": {"available": False, "kind": "unsupported", "description": "现有模型没有经过验证的前后期、伤害类型、开团、保护或控制能力特征，不输出主观评分。"}},
            "limitations": ["这是单局概率模型，不输出 Bo3/Bo5 系列赛胜率。", comparison["limitation"],
                            "历史胜率仅为描述统计，少于20局显示历史样本不足；0局返回空值而非假定50%。",
                            "历史统计严格早于 as_of 且结果已可用，当前目标比赛及未来比赛均被排除。",
                            "名称派生的职业选手身份存在未核验关联；历史观测阵容不等于已确认的当前首发。",
                            "Worlds 26.20 的独立测试仅22局，不能证明可靠的赛事专项准确率或概率校准。"]}
    # The optional decision layer never replaces calibrated phase-one outputs.
    # Missing/invalid decision artifacts leave standard analysis usable.
    from .judgment import build_judgment
    result["judgment"] = build_judgment(normalized, result, selected, feature, metadata, games_path)
    return result
