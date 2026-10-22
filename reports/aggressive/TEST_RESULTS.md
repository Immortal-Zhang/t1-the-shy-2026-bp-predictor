# 激进判断模式 — 实际验证

- 后端全套：263 passed；最终定向回归：55 passed。
- 前端单元：61 passed。
- 生产浏览器：16 passed，0 failed / skipped / flaky，实际 Chrome 与 Playwright WebKit。
- 严格 TypeScript 与生产构建通过。
- 浏览器覆盖默认激进、极限同指数、标准校准概率、保存/刷新/恢复、手机布局及既有完整 BP/Fearless/异常路径。
- 预测使用真实 /analyze；只有服务不可用负向测试注入503，没有注入胜率。
- 后端覆盖真实推理一致性、时间隔离、未知输入、稀疏样本、证据方向、完整 SHAP 分组和产物损坏拒绝。
- 标准模型及9,309个既有概率保持不变。训练与历史评测分别见 experiment_results.md、judgment_evaluation.md。

真实回放的标准蓝方校准概率 0.3021779236，增强判断蓝方校准概率 0.3390241677。支持指数另行标记，不是概率。

完整证据：TEST_RESULTS.json、实际执行日志、playwright-results.json、api_smoke.json，以及 screenshots/。

仍有限制：一次种子、既有测试段回顾性使用、仅22局目标赛事、未验证战术属性。未证明整体或强倾向命中率提升。
