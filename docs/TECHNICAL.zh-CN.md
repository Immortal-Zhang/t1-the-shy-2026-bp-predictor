# T1.the shy 2026 BP Predictor — 技术资料

日常使用现在只需在克隆目录执行 `./start.sh`（Mac 可双击 `start.command`）。启动器安装依赖，从 [GitHub Release](https://github.com/Immortal-Zhang/t1-the-shy-2026-bp-predictor/releases/tag/runtime-2026-10-22-v1) 下载实际训练好的模型及推理数据，校验 SHA-256 后启动，**不重新训练**。

已手动下载包时可执行 `./start.sh --archive /path/to/t1-the-shy-2026-runtime-v1.tar.gz`；只准备环境使用 `./start.sh --setup-only`。校验已安装产物：`.venv/bin/python scripts/download_runtime.py --check-only`。不同本地产物会保留；只有明确指定下载器的 `--replace` 才备份并替换。

默认前端 5173、API 8026；需要另开一份时使用 `WORLDS_WEB_PORT=5174 WORLDS_API_PORT=8027 ./start.sh`。启动器只复用同一目录实例，不会停止其他项目服务。首次安装需要网络；后续使用本地模型，官方版本核验和英雄头像仍可能访问网络。

以下保留原始开发与重训练说明；除非主动更新模型，普通使用者无需执行训练步骤。

使用**真实职业比赛**训练的单局赛前胜率预测系统。第二阶段提供 React 中文 BP 分析工作台，接入原有 CatBoost/FastAPI 模型；没有模型或模型时间不合法时拒绝预测，不生成演示胜率。

## 激进判断模式

网站现在默认显示**激进模式**，可切换标准模式和极限判断模式。标准模式保留原 `C_catboost_uniform` 的校准概率；实验判断使用独立训练、仅按验证期规则选择的增强 CatBoost。极限模式改变结论措辞和风险排序，不改变胜者、支持指数或优势等级。

激进模式显示明确预测胜者、双方支持指数、综合倾向等级、三个实际模型依据、两个反向因素、BP 净贡献/首要弱点、判断主要依赖 BP 还是选手战队历史，以及数据可靠性。完整 SHAP 分组来自当次判断模型，原标准模型的 SHAP 单独标记。证据不足就注明缺口，不补写英雄能力或虚构三条优势。预测历史保留当时的判断和概率，手工赛果仍标为未经来源核验。

**支持指数不是获胜概率。** 设增强模型原始对数胜算为 `r`，独立 sigmoid 校准器为 `sigmoid(a*r+b)`，其决策边界为 `t=-b/a`。在验证期绝对分差 `abs(r-t)` 的经验分布中计算本局排位 `q`：蓝方支持指数为 `50 + 50*sign(r-t)*q`，红方为 `100-蓝方`。精确概率平局按预先声明的蓝方规则选择、指数保持 50/50 并显式标记。没有65%最低胜率，也没有把校准51%当作80%概率。技术详情同时提供原校准概率、判断模型自身的校准概率与原始分差。

综合等级以胜者指数 `<65 / 65–85 / >=85` 分为轻微、明显、强烈倾向。强烈倾向额外要求验证参考组至少100局，95% Wilson下界至少60%；不达标会降为明显优势。验证组是规则拟合数据，不是独立表现证据。BP 净贡献与综合等级分开，不能把选手优势叫作 BP 优势。

### 真实训练与验证结果

本轮实际训练3个预声明候选，新增190个历史特征，总计374列：90天衰减状态、近期熟练度/对位、当前版本选手英雄历史、明确中野/下路英雄及选手搭档、同阵容经验和交手历史。所有历史结果均严格早于比赛时间及 `as_of`；未加入当前局经济、KDA等赛后输入。

训练/验证/独立校准/既有测试分别为 **15,717 / 2,968 / 716 / 9,309** 局。按验证 AUC 与 Log Loss 门槛选中 `enhanced_recent90_d4`，**没有依据测试集改选另一个分数更高的候选**。

| 9,309 局真实测试 | Accuracy | ROC-AUC | Log Loss | Brier |
|---|---:|---:|---:|---:|
| 原标准模型 | 63.95% | 0.697653 | 0.630171 | 0.220150 |
| 增强实验判断 | 63.64% | 0.692046 | 0.633306 | 0.221484 |

本轮**未证明整体区分能力提高**。该2026测试段已经在前阶段查看，本轮是回顾性研究比较，不是全新确认性评估。标准模型文件和9,309个原预测保持不变。

| 实验判断等级 | 真实场次 | 命中率 | 覆盖率 |
|---|---:|---:|---:|
| 轻微优势 | 2,649 | 51.26% | 28.46% |
| 明显优势 | 3,963 | 62.93% | 42.57% |
| 强烈倾向 | 2,697 | 76.83% | 28.97% |

强倾向95% Wilson区间为75.20%–78.38%，未校正同日/系列赛相关性。原模型按相同策略的强倾向命中率为78.02%，因此也不能声称强倾向命中率有所提高。目标 Worlds 版本只有22局；任何该赛事的高命中小分组都不足以证明可靠性。

### 复现与故障处理

```bash
# 项目根目录，复用现有真实数据及第一阶段模型
.venv/bin/python scripts/train_aggressive.py
.venv/bin/python scripts/evaluate_aggressive.py
.venv/bin/python -m pytest -q
cd frontend
PATH=/opt/homebrew/bin:$PATH npm run test
PATH=/opt/homebrew/bin:$PATH npm run build
# 先启动本地前后端，再执行真实浏览器测试
PATH=/opt/homebrew/bin:$PATH npx playwright test --config playwright.aggressive.config.ts
```

正常使用仍运行 `./scripts/start_local.sh --production`，无需重新训练。更新代码后重启已有后端。增强产物位于 `models/aggressive-experiment/latest/`，策略及真实评估位于 `reports/aggressive/`；原模型位于 `models/latest/`，两者分离。完整逐局预测和真实赛果对照见 `reports/aggressive/judgment_predictions.csv`，Worlds子集见 `judgment_worlds_predictions.csv`。CSV/Parquet/二进制模型留在本地，复现脚本和指标提交Git。

`POST /analyze` 原请求不变，新增响应 `judgment`。有效时包含 `winner`、`support`、`advantage`、`reasons`、`risks`、`bp_assessment`、`driver`、`reliability`、`evaluation`；产物缺失、哈希不符或模型/策略时间不合法时返回 `judgment.available=false` 及原因，仍保留合法的标准预测。原 `POST /predict` 完全保留。旧历史快照没有判断字段时不会自动补造解释。

运行路径可通过 `WORLDS_ENHANCED_MODEL_DIR` 和 `WORLDS_JUDGMENT_DIR` 显式配置。受信任的本地模型、特征实现、策略与评估文件均做哈希校验；API 不接受上传模型。参见 [实验报告](../reports/aggressive/experiment_results.md)、[等级回测](../reports/aggressive/judgment_evaluation.md)。

实际验证完成：**263项 Pytest、61项 Vitest、16项 Chrome/WebKit 生产端到端测试**通过，最终小修后55项定向回归通过；严格 TypeScript 和生产构建通过。详见 [测试报告](../reports/aggressive/TEST_RESULTS.md)。独立同系列模型复核为 **WARN（证据范围限制）**：真实标签与计算可复现，不支持总体/强倾向改善或世界赛专项可靠性主张，详见 [审计](../reports/aggressive/EXPERIMENT_AUDIT.md)。`AUDITED_SNAPSHOT.json` 固定复核时的运行源码与证据；`DELIVERY_MANIFEST.json` 另外绑定最终文档、审计报告及截图。

**尚未支持**：经过验证的控制/开团强度、前中后期阵容曲线和战术风格克制。现有数据能支持组合历史关联，不能将其包装为确定性战术因果。后续应补充带来源及版本日期的战术特征、做消融与多时间窗口验证，并用数据截止日之后的新比赛检验泛化。

## 第二阶段：启动完整网站

本目录已有第一阶段虚拟环境、真实数据和模型时：

```bash
./scripts/start_local.sh
```

打开 **http://127.0.0.1:5173**。API 文档为 **http://127.0.0.1:8026/docs**。脚本检查并复用同一项目的现有服务，不停止端口上的其他应用；Ctrl+C 仅停止本次脚本启动的进程。要先构建再本地运行，使用 `./scripts/start_local.sh --production`。源代码更新后应重启已有后端。

前后端也可分别启动：

```bash
# 终端 1，项目根目录
.venv/bin/uvicorn worlds_predictor.api:app --host 127.0.0.1 --port 8026

# 终端 2
cd frontend
npm ci
npm run dev
```

要求 Python 3.11+、Node.js 20.19+（20.x）或 22.12+，以及 npm。本机 Codex 内嵌 Node 无法加载 Vite 的原生绑定，启动脚本自动优先使用 `/opt/homebrew/bin/node`；手动执行时可用 `PATH=/opt/homebrew/bin:$PATH npm run dev`。没有更改任何系统签名或安全设置。前端通过 Vite `/api` 代理连接本机 FastAPI，无付费云服务依赖。

第一阶段环境/模型缺失时，先执行下面的原始数据与训练流程；网站会明确显示模型不可用。英雄资料和赛事参考 JSON 位于 `data/catalog/`，可以独立更新：

```bash
.venv/bin/python scripts/update_catalog.py
```

### 已实现的网站功能

- 官方来源核验的 19 支参赛队伍搜索；按赛前时间加载最近实际出场阵容，显示日期并允许手动换人。**历史首发不等于当前注册首发**。
- 173 个 Riot Data Dragon 中英文英雄、头像、历史位置筛选、10 个角色选位及双方五个 ban；重复选取、禁用冲突与无效输入拦截。
- 蓝红交换、独立先选权、重置英雄、清空 BP、保存草稿、恢复真实比赛 BP。变更输入立即使旧预测失效；过期异步响应不会覆盖新阵容。
- 调用真实 `/analyze`：保存的 B CatBoost 与部署 C 模型对比、两侧胜率、历史样本覆盖、选手熟练度、位置对线、20 个两两阵容组合及原生 SHAP。
- 22 场数据覆盖范围内的真实 Worlds 26.20 比赛，含来源赛果。加载时采用该局赛前 `as_of`，赛果不会作为请求字段发送。
- Bo3/Bo5 全局 Fearless 的前序小局选用记录与禁选限制，仅在已核验的 Worlds 2026 范围启用；不输出系列赛胜率。
- 浏览器本地预测快照与阵容草稿，按比赛日期排序、手动录入实际赛果、恢复/删除/确认清空；刷新保留状态，历史结果不随模型更新改写。手动赛果明确标记为用户录入。

### 网站测试与证据

```bash
.venv/bin/python -m pytest -q
cd frontend
PATH=/opt/homebrew/bin:$PATH npm run test
PATH=/opt/homebrew/bin:$PATH npm run build
PATH=/opt/homebrew/bin:$PATH npx playwright install chromium webkit
# 先运行 8026 后端及 5173 前端
PATH=/opt/homebrew/bin:$PATH npm run test:e2e
```

测试记录、实际浏览器截图和复核报告保存在 `reports/phase2/`；汇总见 [TEST_RESULTS.md](../reports/phase2/TEST_RESULTS.md)。已执行 219 项 Pytest、44 项 Vitest、12 项 Chrome/WebKit 端到端测试，并在生产构建上再验证 4 项实际 BP 与完整预测流程，均通过。端到端预测使用真实 API，仅“服务不可用”负向场景注入 503 错误；不会注入假的获胜概率。工程测试夹具与产品训练数据隔离。

### 新接口与参考资料边界

`GET /catalog?as_of=...`、`GET /teams?as_of=...&worlds_only=true`、`GET /teams/{id}/roster?as_of=...`、`GET /matches?as_of=...&worlds_only=true` 和 `POST /analyze` 与旧接口并存。

`/analyze` 接收原 PredictionRequest，额外允许 `draft_context`：

```json
{"enabled": true, "format": "bo3", "previous_games": [{"blue_champions": ["五个实际选用英雄"], "red_champions": ["另五个实际选用英雄"]}]}
```

以上仅描述结构，数组实际必须各含五个不同且可识别的英雄；不是可用于真实预测的样例。完整可执行请求由网站或 `examples/real_match_replay.json` 提供。英雄可用精确英文、中文名、称号或 Data Dragon ID，规范化后再次检查冲突。未知职业稳定 ID 可以输入，但缺少历史会显式显示；未知英雄不会被猜测。

当前参赛公告仅有 2026-10-05 日期，因此保守使用 **2026-10-06 00:00 UTC** 作为资格可用边界，要求早于 `as_of`。该日期之前不会展示未来参赛资格。当前公告快照仍不能证明其内容从未修订。Roster API 只依据更早已知赛果中的实际出场，不调用个人排位账号。

英雄头像和文本来自 [Riot Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon)，参赛名单来自 [官方 Worlds 公告](https://lolesports.com/en-GB/news/worlds-2026-primer)，Fearless 来源与精确规则节保存在 `data/catalog/worlds_rules.json`。JSON 缓存、URL、获取日期和 SHA-256 均保留。没有已核验复用许可的战队标志使用**中性缩写徽标**，不冒充官方队徽。

页面含 Riot 要求的非官方声明，不提供博彩功能。公开服务/发行前仍须按 [Riot 开发者政策](https://developer.riotgames.com/policies/general)处理产品注册和审核；本轮仅交付本地研究工具，没有代替用户注册、发布或声称官方认可。

### 当前明确不支持的结论

- 没有官方逐局首发确认服务、完整人工身份核验或已授权的全套战队队徽。
- 不输出未经验证的前后期、伤害类型、开团、保护、控制评分；当前以真实历史统计与模型特征解释为准。
- B 使用近期权重、部署 C 使用均匀权重，二者校准参数也独立拟合；差值不能视为 BP 因果效应。
- SHAP 解释原始 log-odds，最终概率另经校准；零样本显示未知，少于 20 场标为样本不足。
- 无完整 Bo3/Bo5 胜率模型、无跨浏览器云同步、无自动核验用户手工赛果。自定义赛事不能套用已核验的 Worlds Fearless 规则。
- 公布版本 `26.20` 与来源 `16.20` 有明确映射；其他公开/内部版本不能自动类推，缺少该版本历史会显示覆盖不足。
- 目标 Worlds 版本只有 22 个独立测试样本，尚不支持可靠的 Worlds 专项准确率或校准主张。

原阶段评测与审计保留为冻结训练产物；第二阶段代码与测试证据独立保存在 `reports/phase2/`，没有将新增界面误称为新训练实验。

## 快速运行

```bash
cd worlds-2026-bp-predictor
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
python -m pip install -e '.[dev]'

worlds-bp download --years 2024 2025 2026
worlds-bp normalize --as-of 2026-10-22T00:00:00Z
worlds-bp train --config configs/train.json
pytest -q

# 生成真实历史比赛的赛前重放请求，绝不虚构比赛
worlds-bp make-replay
worlds-bp predict examples/real_match_replay.json --output reports/replay_prediction.json
uvicorn worlds_predictor.api:app --host 127.0.0.1 --port 8026
```

```bash
curl http://127.0.0.1:8026/health
curl -X POST http://127.0.0.1:8026/predict \
  -H 'Content-Type: application/json' \
  --data-binary @examples/real_match_replay.json
```

默认服务仅绑定本机。服务器部署的认证、访问控制和限流需由部署环境补充。模型为受信任的本地 joblib 文件；API 不接受上传或任意指定模型文件。

## 数据与使用条件

- 主来源：[ChainCC Open Dataset](https://chaincc.lol/free/data/)，页面声明 **CC BY 4.0**，须保留 attribution：`ChainCC. League of Legends esports match dataset. https://chaincc.lol/free/data/`。本项目进行了清洗、隔离、身份规范化和历史特征转换。
- [Oracle's Elixir](https://oracleselixir.com/tools/downloads) 为备用来源；本次访问为 403，未伪造备用数据。其许可须另行核验，不能套用 ChainCC 许可。
- 原始文件下载/导入时间、URL、字节数、SHA-256、实际 CSV 日期覆盖保存在 `data/raw/sources.json`；完整原始字段列表保存在 `data/processed/quality_report.json`。
- 网站更新时间与实际比赛覆盖截止不同。以 CSV 最大比赛时间为准，详见 `SOURCE_DATA.md` / 程序生成的数据质量报告。
- 不向 Git 提交原始数据、私人原有文件、虚拟环境或二进制模型。真实下载和模型产物保存在本地；报告和复现代码提交 Git。

下载失败时仍会写出逐文件失败状态。不要把失败文件或 HTML 当作 CSV；可以人工下载原始文件后导入：

```bash
# ChainCC：同一年选手表和战队表都要导入
worlds-bp import-csv /absolute/path/chaincc-players-2026.csv.gz \
  --raw-dir data/manual --source-url https://chaincc.lol/free/data/ --license 'CC BY 4.0; attribution required'
worlds-bp import-csv /absolute/path/chaincc-teams-2026.csv.gz \
  --raw-dir data/manual --source-url https://chaincc.lol/free/data/ --license 'CC BY 4.0; attribution required'

# OE 原始年度 CSV 本身应同时含选手行和 position=team 战队行
worlds-bp import-csv /absolute/path/original-2026.csv \
  --raw-dir data/manual-oe --source-url https://oracleselixir.com/tools/downloads \
  --license 'unknown; operator must verify source terms'
worlds-bp normalize --raw-dir data/manual-oe --output-dir data/processed-oe --as-of 2026-10-22T00:00:00Z
```

人工导入的来源信息由操作者提供并标为未独立验证；不知道原下载日期就保留未知。不要混合多个来源版本冒充同一可信快照。下载命令默认复用并校验现有文件；更新数据时请使用新的 `--raw-dir`，保留旧快照以复现。

## 数据质量与身份

`games.parquet` 和 `games.duckdb` 中的 `games` 表每局只有一行。唯一键 `game_id`，保留 UTC 时间、结果可用边界、联赛、版本、蓝红队伍、十名选手、各自位置/英雄、双方五个 ban 与先选权。

选手/战队通过 **`game_id` + `side`** 连接，并验证 many-to-one。检查两支不同队伍、每侧五个不同位置、十个不同选手和英雄、队伍一致性、互补胜负、team pick 与选手英雄一致性及异常 BP。问题比赛写入 `quarantine.csv`，不静默补齐标签。缺失 ban 保留 unknown；与“确定没有禁用”不同。

ChainCC 当前 CSV **没有不可变的职业选手 ID**。本系统为精确职业显示名建立确定且可复现的 `pro:<UUID>` 本地身份；不会依赖个人排位账号，也不做模糊名称合并。它只能保证注册表内部稳定，**不能证明同名是同一人，也不能自动证明改名是同一人**。这些关联在报告/API 中标为未核验，不能声称已完成人工身份金标准。

`player_registry.csv` 保存别名、身份依据和首次/最后观测日期；`player_team_stints.csv` 保存观测到的连续队伍变化。日期是观测边界，不是猜测的合同或官宣转会日期。外部核实后，在 `configs/player_aliases.csv` 填写 `alias,canonical_id,valid_from,valid_to`（UTC，左闭右开）；使用：

```bash
worlds-bp normalize --as-of 2026-10-22T00:00:00Z --aliases configs/player_aliases.csv
```

身份映射变化后应重新训练。请求优先使用注册表内职业选手 ID；别名查询必须带 `as_of`，不能从未来名单推断历史阵容。

```bash
worlds-bp players --query Faker --as-of 2026-10-22T00:00:00Z
curl 'http://127.0.0.1:8026/players?query=Faker&as_of=2026-10-22T00%3A00%3A00Z'
```

运行时显式别名映射可通过 `WORLDS_ALIASES_PATH` 指定，必须与规范化数据时采用的同一映射一致。

## 特征与时间边界

| 级别 | 特征 |
|---|---|
| A | 地图蓝红方视角、独立先选权、联赛、战队 ID、历史/最近 20 局队伍胜负表现 |
| B | A + 位置化职业选手 ID、选手历史和最近 20 局表现 |
| C | B + 位置化十英雄、十 ban、版本、选手英雄熟练度、位置对线历史、两两英雄搭配、版本内英雄历史表现 |

每级先训练正则化 Logistic Regression，再训练 CatBoost。高基数类别用稀有类别合并/模型正则化，低样本组合用 Beta 平滑并保留实际样本数。对称先验只是稀有样本的统计平滑，不是人工英雄评分或返回给用户的固定胜率。当前局 KDA、经济、伤害、目标控制不会进入特征；本阶段仅用更早比赛的真实胜负形成历史状态。

历史事件须同时满足 `date < cutoff` 和 `available_at < cutoff`。数据加载使用 DuckDB 条件下推；同一时间的比赛不会互相读结果；同一 game_id 不会跨训练/测试重复。由于来源未保证 `date` 的起止语义与原始发布时间，结果可用边界保守设为 `max(下一 UTC 零点, date + gamelength + 1 小时)`。`gamelength` 仅用于隔离未完赛标签，绝非当前预测输入。该策略舍弃同日信息以防泄漏，仍不能把今天下载的修订快照等同于历史时点供应商归档。

预测要求 `as_of <= scheduled_start`，且严格晚于所用模型训练/选择/校准标签的最大可用时间。想预测更早历史时点，必须用当时之前的数据重训相应模型。最终 BP 必须在用户指定 `as_of` 时已知；本 API 是 BP 结束后、比赛开始前的单局预测。

## 真实回测与结果

默认配置：

| 阶段 | 比赛时间（UTC） | 用途 |
|---|---|---|
| 训练 | 2024-01-01 至 2025-07-01 之前 | 拟合模型和类别处理 |
| 验证 | 2025-07-01 至 2025-10-01 之前 | 仅按 raw Log Loss 选择模型 |
| 校准 | 2025-10-01 至 2026-01-01 之前 | 单独拟合 sigmoid 概率校准 |
| 独立测试 | 2026-01-01 至 as_of 之前 | 未参与模型选择或校准 |

各段末尾尚不可用的结果会被清除。模型参数在测试期间冻结；滚动历史可在更早测试比赛的结果已可用之后更新，属于时间递进的赛前回测。它不等于整个 2026 年只使用 2025 年底历史的静态预测。

`reports/metrics.json`、`RESULTS.md`、`predictions_*.csv`、`split_membership.csv` 均由程序生成，含 Accuracy、ROC-AUC、Log Loss、Brier Score、校准分箱和 ECE。报告原始及校准概率；校准集分数属于校准拟合集，不充当独立结果。保留 Logistic 系数、CatBoost 特征重要性和全部模型产物。

B 与 C 使用相同测试比赛比较，提供按天成块的 paired bootstrap Log Loss 差异区间；C 同时增加 BP 和版本，**不是 BP 的因果收益证明**。另跑无近期权重的 C 模型，与 180 天半衰期权重比较；分版本、联赛、月份、训练见过/未见过联赛给出样本覆盖和指标。小样本分组不支持稳定结论。本轮只有一个时间切分和一个训练种子，不保证准确率，也不能把全部职业联赛测试分数当作 Worlds 专项准确率。

无权重 C 是预先声明的模型选择候选，同时用于近期权重敏感性比较。补充的 LCK 训练标签池实验和图表可复现：

```bash
python -m worlds_predictor.sensitivity
python -m worlds_predictor.sensitivity --raw
python -m worlds_predictor.plots --metrics reports/metrics.json --output reports/calibration.png
python tests/smoke_live_api.py   # 先在 8026 启动服务
```

默认时间切分中 LCK 校准集为零，因此单独 LCK 校准比较会如实标记 blocked；`--raw` 比较未校准的双方概率，并共享相同 LCK 测试比赛。两组沿用全球历史特征，所以它仅评估训练标签混合，不能称为彻底隔离赛区的迁移测试。

部署模型由验证集决定，不强制选 C。如果 BP 没改善，会直接报告。默认模型不在测试集上重训，保持该独立测试结论可复现。线上响应含模型版本、训练标签截止时间、历史数据截止、实际样本覆盖和未知组合。

## Worlds 2026 / API 契约

`configs/worlds2026.json` 设置版本 **26.20**。API 启动和 CLI 预测会联网核对 [Riot 官方 26.20 公告](https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-20-notes/)，记录核验时间与正文哈希。核验失败显示 unverified；发现官方版本与配置冲突则拒绝 Worlds 预测。当前公告核验不承诺覆盖之后的新规则修订。

数据源使用联赛 `WLDs` 和内部版本 `16.20`，Riot 公告使用公开版本 `26.20`（[Data Dragon 版本表](https://ddragon.leagueoflegends.com/api/versions.json)列出 `16.20.1`）。系统保留原始训练值，显式将这对版本别名映射到同一个模型特征，并在响应中同时返回 `input_patch/model_patch`。Worlds、WLDs、WCS、World Championship 都经过同一版本检查；其他未登记的公开版本不会擅自套用此对应关系。

请求字段：`as_of`、`scheduled_start`、`league`、`patch`、`blue`、`red`、`first_pick_side`；`game_id` 可选。两侧各有 `team_id`、五名 `players`（`role/player_id/champion`）以及最多五项 `bans`（未知用 null）。支持位置 `top/jng/mid/bot/sup`，英雄名沿用来源中的标准英文名。地图 side 由 blue/red 对象表示，先选权单独传 blue/red/unknown，绝不推断“蓝方必先选”。非空 `series_context` 暂时拒绝，给未来 Bo3/Bo5 Fearless Draft 留接口而不伪装已实现系列赛预测。

环境变量：`WORLDS_MODEL_DIR`、`WORLDS_GAMES_PATH`、`WORLDS_CONFIG`、`WORLDS_VERIFICATION_REPORT`。文件完整性不符或特征实现已改变时拒绝旧模型预测，需要重训。无模型为 HTTP 503；非法请求、未来模型用于过去预测为 422。

## 目录

```text
configs/              可复现训练、Worlds 和人工核验别名配置
data/raw/             原始 CSV 与来源清单（本地）
data/processed/       一局一行 Parquet / DuckDB、注册表、隔离和质量报告
src/worlds_predictor/ 导入、历史特征、训练评测、CLI、API
models/               每次运行的真实模型及 latest 指针副本（本地）
tests/                单元、数据质量、时间泄漏、模型与 API 测试
reports/              真实评价、预测、来源、审计和运行日志
examples/             来自真实比赛的历史重放请求与来源说明
PROGRESS.md           完成状态、限制与实际命令
```

测试中的小型合成夹具只验证工程不变量；不参与产品训练，也不进入真实指标。需要持续更新原始 CSV、复核身份映射和滚动重训；模型输出始终是有数据覆盖边界的统计估计。
