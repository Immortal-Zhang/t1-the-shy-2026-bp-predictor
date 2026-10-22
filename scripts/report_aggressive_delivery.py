"""Generate delivery evidence from executed logs and actual experiment artifacts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/aggressive"


def read(name):
    return json.loads((REPORTS / name).read_text())


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    pytest_log = (REPORTS / "pytest.log").read_text()
    targeted_log = (REPORTS / "final-targeted-pytest.log").read_text()
    frontend_log = re.sub(r"\x1b\[[0-9;]*m", "", (REPORTS / "vitest.log").read_text())
    build_log = (REPORTS / "build.log").read_text()
    playwright = read("playwright-results.json")["stats"]
    if playwright["unexpected"] or playwright["flaky"] or playwright["skipped"]:
        raise RuntimeError("Browser suite was not fully successful")
    if re.search(r"\d+ failed", pytest_log + targeted_log + frontend_log) or "built in" not in build_log:
        raise RuntimeError("Test/build evidence contains failures or is incomplete")
    experiment = read("experiment_metrics.json")
    evaluation = read("judgment_evaluation.json")
    selected = experiment["models"][experiment["selected_candidate"]]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pytest": {"passed": int(re.findall(r"(\d+) passed", pytest_log)[-1]), "log": "pytest.log"},
        "final_targeted_pytest": {"passed": int(re.findall(r"(\d+) passed", targeted_log)[-1]), "log": "final-targeted-pytest.log"},
        "vitest": {"passed": int(re.search(r"Tests\s+(\d+) passed", frontend_log).group(1)), "log": "vitest.log"},
        "playwright": playwright,
        "build": "Strict TypeScript + Vite production build passed",
        "browsers": {name: read(f"aggressive-browser-{name}.json") for name in ("chromium", "webkit")},
        "model_reuse": read("experiment_reproducibility.json"),
        "standard_test": experiment["baseline"]["test_calibrated"],
        "enhanced_test": selected["test_calibrated"],
        "judgment_test": evaluation["deployment_test"],
        "api_smoke": read("api_smoke.json"),
        "limits": ["The 2026 test period was inspected earlier; this is retrospective evidence.",
                   "No overall or strong-call improvement demonstrated.",
                   "Only 22 target-patch Worlds games; no event-specific reliability claim.",
                   "No validated crowd-control/engage/game-phase/style ratings.",
                   "Full browser workflows covered Chrome and Playwright WebKit; no new full native Safari claim."]}
    (REPORTS / "TEST_RESULTS.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    markdown = ["# 激进判断模式 — 实际验证", "",
                f'- 后端全套：{summary["pytest"]["passed"]} passed；最终定向回归：{summary["final_targeted_pytest"]["passed"]} passed。',
                f'- 前端单元：{summary["vitest"]["passed"]} passed。',
                f'- 生产浏览器：{playwright["expected"]} passed，0 failed / skipped / flaky，实际 Chrome 与 Playwright WebKit。',
                '- 严格 TypeScript 与生产构建通过。',
                '- 浏览器覆盖默认激进、极限同指数、标准校准概率、保存/刷新/恢复、手机布局及既有完整 BP/Fearless/异常路径。',
                '- 预测使用真实 /analyze；只有服务不可用负向测试注入503，没有注入胜率。',
                '- 后端覆盖真实推理一致性、时间隔离、未知输入、稀疏样本、证据方向、完整 SHAP 分组和产物损坏拒绝。',
                '- 标准模型及9,309个既有概率保持不变。训练与历史评测分别见 experiment_results.md、judgment_evaluation.md。',
                '', '真实回放的标准蓝方校准概率 ' + f'{summary["api_smoke"]["standard_blue"]:.10f}' +
                '，增强判断蓝方校准概率 ' + f'{summary["api_smoke"]["enhanced_blue"]:.10f}' + '。支持指数另行标记，不是概率。',
                '', '完整证据：TEST_RESULTS.json、实际执行日志、playwright-results.json、api_smoke.json，以及 screenshots/。',
                '', '仍有限制：一次种子、既有测试段回顾性使用、仅22局目标赛事、未验证战术属性。未证明整体或强倾向命中率提升。']
    (REPORTS / "TEST_RESULTS.md").write_text("\n".join(markdown) + "\n")
    # Bind runtime explanations as well as trained features. Exclude only the
    # manifest itself and generated browser report bundles; never self-hash.
    patterns = ["src/worlds_predictor/*.py", "scripts/*.py", "tests/*.py", "configs/*.json",
                "frontend/src/**/*.ts", "frontend/src/**/*.tsx", "frontend/src/*.css", "frontend/e2e/*.ts",
                "frontend/*config*.ts", "frontend/*config*.json", "frontend/package*.json",
                "reports/aggressive/*", "reports/aggressive/screenshots/*.png",
                "models/latest/metadata.json", "models/latest/selected_model.joblib",
                "models/aggressive-experiment/latest/*", "README.md", "PROGRESS.md"]
    files = sorted({path for pattern in patterns for path in ROOT.glob(pattern)
                    if path.is_file() and path.name != "DELIVERY_MANIFEST.json"})
    manifest = {"generated_at": summary["generated_at"], "scope": "Local delivery integrity; hashes are not external signatures",
                "files": {str(path.relative_to(ROOT)): {"sha256": sha(path), "bytes": path.stat().st_size} for path in files}}
    (REPORTS / "DELIVERY_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"pytest": summary["pytest"]["passed"], "vitest": summary["vitest"]["passed"],
                      "playwright": playwright["expected"], "manifest_files": len(files)}))


if __name__ == "__main__":
    main()
