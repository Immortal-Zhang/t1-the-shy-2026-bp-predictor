# LOL Worlds 2026 BP Predictor

[English](README.md) · **简体中文** · [한국어](README.ko.md)

基于真实《英雄联盟》职业比赛训练的赛前单局预测系统。React BP 工作台连接 FastAPI 和 CatBoost，支持完整阵容输入、校准胜率、实验性激进判断、历史统计与模型解释。没有有效模型时拒绝预测，不返回随机数或固定胜率。

![激进判断工作台实际运行截图](reports/aggressive/screenshots/chromium-aggressive.png)

## 功能与边界

- 输入蓝红双方战队、10 名职业选手、10 个对应位置的英雄、双方 ban、比赛版本、赛前时间 `as_of` 和独立 BP 先选权。
- 搜索 19 支核实的 Worlds 2026 参赛队伍和 173 位中英文英雄；按日期加载最近观测出场阵容，允许手动换人。历史出场不代表已确认的当前首发。
- 交互式 BP 编辑、交换阵营、重置、重复/禁用冲突拦截；输入改变后旧结果失效。**仅在完整 BP 后预测，不支持未完成 BP 的逐手实时胜率。**
- 标准模式显示原校准概率；默认激进模式显示明确胜者、双方支持指数、综合倾向等级、三个依据、两个风险、BP 净贡献和数据可靠性。极限模式只改变表达与证据顺序，不改变激进判断数值。
- 比较 BP 前后模型，展示原生 SHAP、选手英雄历史、同位置对位和组合统计；这些是统计关联与模型贡献，不是战术因果证明。
- 保存本地预测快照、恢复 BP、录入赛果并对比；旧记录保留原模型结果。手工赛果标明未经来源核验。
- 支持已核验 Worlds 规则下的 Bo3/Bo5 Fearless 前序英雄约束，Bo5 最多记录四局。**预测仍针对当前单局，不输出整场系列赛胜率。**

技术栈：Python、Pandas、DuckDB、CatBoost、Scikit-learn、FastAPI、Pytest；React、TypeScript、Vite、Tailwind CSS、Zustand、Recharts、Vitest、Playwright。

## 首次克隆与启动

需要 Python 3.11+、Node.js 20.19+（20.x）或 22.12+，以及 npm。仓库包含源码、配置、目录缓存和已记录的评测证据；**不附带原始 CSV、处理后的比赛数据、虚拟环境或模型二进制文件**。首次克隆必须下载真实数据并训练，不能直接把历史报告当作可加载模型。

在项目根目录执行：

```bash
git clone https://github.com/Immortal-Zhang/lol-worlds-2026-bp-predictor.git
cd lol-worlds-2026-bp-predictor
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install -e '.[dev]'
npm --prefix frontend ci

# 下载、校验和训练原标准模型
worlds-bp download --years 2024 2025 2026
worlds-bp normalize --as-of 2026-10-22T00:00:00Z
worlds-bp train --config configs/train.json

# 生成独立增强模型及激进判断策略；启用激进判断时需要
python scripts/train_aggressive.py
python scripts/evaluate_aggressive.py

./scripts/start_local.sh --production
```

网站：**http://127.0.0.1:5173**。API 文档：**http://127.0.0.1:8026/docs**。启动脚本复用本项目已有服务；Ctrl+C 只停止本次脚本启动的进程。修改后端源码后需要重启已有后端。

只使用标准预测时，可以跳过两个激进训练/评估命令；网站会明确显示激进判断不可用。缺少标准模型时，预测接口返回 503，不生成假结果。数据源之后的修订可能改变训练结果，不能保证重新下载后得到完全相同的历史指标。

英雄和赛事参考 JSON 已缓存；需更新时运行 `python scripts/update_catalog.py`。数据源不可访问时，可使用 `worlds-bp import-csv` 导入本地 CSV；完整导入、别名和时间配置说明见 [技术指南](docs/TECHNICAL.zh-CN.md)。

macOS 启动脚本会优先使用存在的 Homebrew Node。若终端选中了无法加载 Vite 原生绑定的应用内嵌 Node，可使用 `PATH=/opt/homebrew/bin:$PATH npm --prefix frontend run build`。这不需要修改系统签名。

## 真实数据与时间隔离

已记录的源快照覆盖至 **2026-10-18 19:48:36 UTC**，清洗后保留 **28,738 局**；目标 Worlds 版本样本仅 **22 局**。原模型训练、选择和校准使用的标签最晚可用时间为 **2025-12-30 00:00 UTC**。

标准化表每局一行，选手与战队按 `game_id + side` 对齐；验证每侧五名选手、五个正确位置及一致赛果。当前比赛的 KDA、经济、伤害等赛后数据不进入赛前输入。历史特征只使用 `date < as_of` 且 `available_at < as_of` 的结果，同一比赛不会跨训练和测试两侧。

来源没有不可变职业选手 ID。本地稳定标识由职业显示名及显式别名规则维护；不能自动证明同名或改名属于同一人。转会日期采用观测边界，不冒充合同或官宣日期。

Worlds 默认公开版本为 **26.20**，与当前来源内部版本 **16.20** 显式对应。API 启动时核验官方公告：无法核验会标明状态，若官方版本与配置冲突则拒绝对应预测。

## 已记录的评估结果

按时间顺序划分训练 / 验证 / 独立校准 / 测试：**15,717 / 2,968 / 716 / 9,309** 局。边界上尚不可用的赛果被清除；测试期间模型参数冻结，只滚动更新已可获得的更早历史。

| 9,309 局测试 | Accuracy | ROC-AUC | Log Loss | Brier |
|---|---:|---:|---:|---:|
| 原标准模型 | 63.95% | 0.697653 | 0.630171 | 0.220150 |
| 增强实验判断 | 63.64% | 0.692046 | 0.633306 | 0.221484 |

原标准模型 ECE 为 **0.03134**。增强实验加入 190 个历史特征，共 374 列，并实际训练三个预声明候选；仅按验证 AUC 与 Log Loss 门槛选择模型，没有看测试分数后改选。**本轮未证明整体区分能力提高。** 增强实验复用了前阶段已经查看过的 2026 测试段，属于回顾性研究，不是全新确认性评估。

**支持指数不是获胜概率。** 它表示模型决策分差在验证期分差分布中的相对排位。三种展示模式不会把 51% 校准概率改成 80% 概率，也不设最低胜率。支持指数等级门槛为 65 / 85；“强烈倾向”还要求验证组至少 100 局且 Wilson 95% 下界达到 60%。这些验证数据用于拟合策略，不充当独立命中率。

| 增强判断等级 | 测试场次 | 命中率 |
|---|---:|---:|
| 轻微优势 | 2,649 | 51.26% |
| 明显优势 | 3,963 | 62.93% |
| 强烈倾向 | 2,697 | 76.83% |

强倾向覆盖 28.97%，Wilson 95% 区间为 75.20%–78.38%，未校正同日或系列赛相关性。原模型按相同策略的强倾向命中率为 78.02%，因此不能宣称强判断改善。22 局目标赛事不足以支持稳定的 Worlds 专项准确率或校准结论。

详见 [原始回测](reports/RESULTS.md)、[增强实验](reports/aggressive/experiment_results.md)、[等级评估](reports/aggressive/judgment_evaluation.md)及[独立复核](reports/aggressive/EXPERIMENT_AUDIT.md)。逐局 CSV 与模型产物由训练、评估程序在本地生成，未随源码提交。

## API 与测试

`POST /predict` 返回原模型校准概率；`POST /analyze` 额外返回 BP 前后比较、真实历史统计、SHAP 和可用的激进 `judgment`。参考查询包括 `/health`、`/players`、`/catalog`、`/teams`、`/teams/{id}/roster`、`/matches`。

使用真实历史比赛生成请求，不手写虚构对局：

```bash
worlds-bp make-replay
curl -X POST http://127.0.0.1:8026/analyze \
  -H 'Content-Type: application/json' \
  --data-binary @examples/real_match_replay.json
```

每侧需 `team_id`、五名 `players`（`role`、`player_id`、`champion`）和最多五项 `bans`；还需 `as_of`、`scheduled_start`、`league`、`patch`、`first_pick_side`。蓝红地图方与先选权分别传入。无效输入为 422；缺少有效标准模型为 503；可选激进产物失效时明确返回 `judgment.available=false`。

```bash
# 完成数据与模型准备后，在项目根目录运行
python -m pytest -q
npm --prefix frontend run test
npm --prefix frontend run build
cd frontend
npx playwright install chromium webkit
# 另一个终端先启动前后端
npx playwright test --config playwright.aggressive.config.ts
```

已实际执行 **263 项 Pytest、61 项 Vitest、16 项 Chrome/WebKit 生产端到端测试**，均通过；最后的定向回归 55 项通过。测试包括真实预测、时间隔离、错误处理、模式切换、历史恢复和手机布局。源码克隆缺少真实产物时，部分集成测试可能跳过；不能把跳过计为真实模型验证通过。参见[测试报告](reports/aggressive/TEST_RESULTS.md)与[Mac 现场核验](reports/acceptance/README.md)。

## 目录

```text
configs/              训练、版本和别名配置
data/                 目录缓存；下载及处理数据在本地生成
src/worlds_predictor/ 数据、特征、模型、CLI 和 API
frontend/             React 工作台与浏览器测试
models/               本地训练产物，不随源码提供
tests/                单元、时间泄漏、数据与 API 测试
reports/              已记录的指标、审计与截图
scripts/              启动、增强训练、评估和现场验证
```

## 来源、许可与限制

- 比赛主来源：[ChainCC Open Dataset](https://chaincc.lol/free/data/)，来源声明 CC BY 4.0。归属：**ChainCC. League of Legends esports match dataset. https://chaincc.lol/free/data/**。本项目进行了清洗、隔离、身份规范化与历史特征转换，详见 [SOURCE_DATA.md](SOURCE_DATA.md)。
- 备用来源：[Oracle's Elixir](https://oracleselixir.com/tools/downloads)。本次访问返回 403，未使用虚构替代数据；其使用条件须独立核验，不能套用 ChainCC 许可。
- 英雄资料和头像来自 [Riot Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon)；赛事资料来源保存在 `data/catalog/`。Riot 素材仍受[开发者政策](https://developer.riotgames.com/policies/general)等适用条款约束。没有核实使用权限的队徽以中性缩写代替。
- 代码尚未指定开源许可证；公开源码不改变数据、商标或第三方素材的各自权利。发布公开服务前需自行满足适用的 Riot 产品注册与政策要求。

这是非官方研究与娱乐分析工具，不提供博彩或投注建议，也不保证预测正确。不提供未经验证的控制/开团评分、前中后期曲线、战术风格克制或系列赛胜率。

LOL Worlds 2026 BP Predictor isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
