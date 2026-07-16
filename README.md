# World Cup Oracle

World Cup Oracle 是一个面向 2026 世界杯的冠军预测与赛程数据 Agent 项目。项目以可验证的赛程、球队特征、进球模型、市场信息和赛前证据为基础，输出可追溯、可复现并明确表达不确定性的概率预测。

当前仓库已经完成了阶段性冠军预测中心、真实赛程同步、严格预测发布契约、历史预测起点回放、结构化 Agent 报告、PostgreSQL 持久化、React 预测页面和 Docker Compose 本地部署。项目仍处在迭代阶段，但冠军预测链路已经从“可运行原型”升级为“宁可空态也不展示错误结论”的真实性优先架构。

## 当前进展

已完成或基本可用：

- FastAPI 后端服务，提供健康检查、预测、赛程、球队、小组、淘汰赛、知识库、Agent 等 API 路由。
- 阶段性冠军预测中心，支持 `current`、`post_group`、`post_r32`、`post_r16`、`post_qf` 等预测起点。
- 历史预测起点回放：保留起点之前已锁定赛果，清空之后结果，再从该阶段重新模拟冠军概率。
- 严格发布契约：只有已发布、数据已验证、质量状态可用、冠军概率非空且概率合计为 1 的结果才会被前端展示。
- 48 队世界杯预测引擎，支持淘汰赛条件模拟、冠军概率、单场预测、未来对阵情景和推理产物输出。
- 多源预测模型，包括球队强度特征、Poisson/比分模型、市场赔率融合、新闻/阵容/环境证据、置信度和蒙特卡洛模拟。
- 单一专业预测主线：所有结论都来自结构化数据、概率模型、赛事路径和可追溯外部证据。
- Agent 研究与问答链路，包括本地上下文、联网检索、正文抓取、RAG 召回、来源引用和回答质量检查。
- 已完赛比赛的赛后复盘链路：按最终比分和赛事阶段检索权威战报，整理关键事件、比赛走势和双方调整，并与赛前预测分支严格隔离。
- Bing 体育世界杯数据同步，包含赛程、淘汰赛、排名、球员统计等结构化数据接口。
- PostgreSQL 仓储层，用于保存同步数据、预测缓存和运行产物。
- React + Vite + TypeScript 前端，包含首页、预测中心、报告、剩余比赛、冠军路径、模型与数据状态。
- Docker Compose，包含 Postgres、API、前端 Nginx 三个服务。
- 单元测试和前端交互测试，覆盖预测发布门禁、历史起点、外部证据、Agent 报告、前端空态和正式读取链路。

仍在完善：

- LLM Agent 对来源冲突、极端检索失败和长篇比赛报道的进一步归并能力。
- 赛前 `pre_tournament` 起点的小组赛完整模拟链路。
- 外部数据源的长期稳定性、异常恢复和更细粒度的数据质量评分。
- 生产部署中的长期任务调度、产物留存和观测告警。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端 | Python 3.10+ / FastAPI / Pydantic v2 / NumPy / psycopg |
| 前端 | React 19 / Vite / TypeScript / Tailwind CSS / ECharts |
| 数据 | YAML 配置 / JSON fixtures / PostgreSQL |
| 运行 | Conda 或 pip / npm / Docker Compose |
| LLM | OpenAI-compatible API，默认示例为 DeepSeek |

## 目录结构

```text
backend/
  scripts/              # 数据同步、预测运行、报告生成等命令
  tests/                # 单元测试与集成测试
  wcpa/
    agents/             # Agent 研究、问答和工具调用逻辑
    api/                # FastAPI 应用与路由
    data/               # 数据源、标准化、仓储层
    features/           # 球队特征构建
    prediction/         # 比赛预测模型
    prediction_release.py # 阶段性预测生成、验证、发布
    prediction_report.py  # 结构化冠军预测报告
    reasoning/          # 解释与推理轨迹
    simulation/         # 小组赛、淘汰赛、冠军模拟
    worldcup/           # 世界杯赛程数据服务
config/                 # 模型权重、规则、数据源、赛事配置
data/
  fixtures/             # 样例数据
  normalized/           # 标准化样例和当前真实数据快照
frontend/               # React 前端
outputs/                # 本地产物目录，默认不提交
```

## 阶段性冠军预测中心

预测中心不是简单读取最新 JSON，而是围绕“预测起点”构建一条完整链路：

- `current`：基于当前赛况，只模拟后续未完成比赛。
- `post_group`：小组赛结束、32 强赛前。
- `post_r32`：32 强结束、16 强赛前。
- `post_r16`：16 强结束、8 强赛前。
- `post_qf`：8 强结束、4 强赛前。
- `post_sf`：半决赛结束、决赛赛前，赛事到达后才可用。
- `pre_tournament`：需要完整小组赛模拟链路，当前明确标记为暂不支持。

历史起点回放会阻止未来信息泄漏：系统不会把生成时刻之后的新闻、赔率、阵容伤停、FIFA 排名或 Elo 缓存塞回过去阶段。缺少当时封存外部证据时，模型只使用该起点之前的赛果切片、历史经验和明确标注的保守派生特征。

前端遵循失败关闭原则：如果指定阶段没有通过验证的正式结果，页面显示产品化空态，不会回退到其他阶段，不会生成均匀概率，也不会把候选产物伪装成冠军预测。

## 本地运行

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

安装后端依赖：

```powershell
$env:PYTHONPATH = "backend"
python -m pip install -e ".[dev]"
```

启动后端：

```powershell
$env:PYTHONPATH = "backend"
python -m uvicorn wcpa.api.server:app --reload --host 127.0.0.1 --port 8000
```

安装并启动前端：

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

前端默认地址：

```text
http://localhost:5173
```

## Docker Compose

`start.bat` 默认启动完整容器环境，PostgreSQL、API 和前端都会归入
`worldcup-oracle` Compose 项目组：

```powershell
start.bat
```

也可以直接执行：

```bash
docker compose --env-file .env --env-file .env.local up --build
```

如需使用本机 Python 和 Vite 调试，请显式运行 `start.bat dev`。该模式只把
PostgreSQL 放入容器，API 和前端作为本机开发进程运行，不应再额外创建独立的
`wcpa-api-preview` 容器。

LLM 和 Firecrawl 密钥通过 Docker secrets 以只读文件注入 API 容器，避免在
Compose 展开配置中输出明文；API-Sports 的本地配置由 `.env.local` 注入。

默认服务：

- API: `http://localhost:8000`
- 前端: `http://localhost:8080`
- PostgreSQL: `localhost:5432`

## 常用命令

运行旧完整赛事模拟脚本（开发调试用，不等同于预测中心正式发布链路）：

```powershell
$env:PYTHONPATH = "backend"
python -m scripts.run_prediction --seed 42 --mode professional
```

生成并发布指定预测起点：

```powershell
$env:PYTHONPATH = "backend"
@'
from wcpa.prediction_release import PredictionReleaseService
print(PredictionReleaseService().run(sync_first=True, anchor="current"))
'@ | python -
```

验证指定预测产物：

```powershell
$env:PYTHONPATH = "backend"
python backend/scripts/validate_artifacts.py --anchor current
python backend/scripts/validate_artifacts.py --anchor post_group
```

同步世界杯数据：

```powershell
$env:PYTHONPATH = "backend"
python -m scripts.sync_real_data
```

同步世界杯场馆与环境数据：

```powershell
$env:PYTHONPATH = "backend"
python -m scripts.sync_worldcup_venues
python -m scripts.sync_match_venues
python -m scripts.sync_venue_elevation
python -m scripts.sync_match_weather
python -m scripts.build_match_environment_features
```

场馆原始资料和人工审核说明放在 `开源数据/世界杯球场数据/`；后端运行时读取 `data/seeds/venues_seed.json` 或 PostgreSQL。

运行测试：

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests/unit -q
cd frontend
npm.cmd test -- --run
```

前端构建：

```powershell
cd frontend
npm.cmd run build
```

## 环境变量

`.env.example` 保留了项目需要的变量名和安全默认值。真实密钥只应放在本地 `.env` 中，不要提交到仓库。

提交代码前应确认 `.env`、`.env.local`、运行日志、抓取缓存、预测产物和前端构建目录仍处于 Git 忽略范围。源码、测试、README 和示例配置中只能出现空值、环境变量读取逻辑或明确的示例占位符，不能写入真实 API Key、数据库密码、访问令牌或浏览器会话数据。

主要变量：

- `WCPA_DATABASE_URL`: PostgreSQL 连接地址。
- `WCPA_BING_SCHEDULE_URL`: Bing 体育世界杯赛程页面地址。
- `WCPA_ENABLE_WEB_COLLECTORS`: 是否启用网页数据采集。
- `WCPA_ENABLE_LLM_AGENTS`: 是否启用 LLM Agent。
- `WCPA_LLM_BASE_URL`: OpenAI-compatible API 地址。
- `WCPA_LLM_MODEL`: LLM 模型名。
- `WCPA_LLM_API_KEY`: 本地私有 API Key。
- `WCPA_WEB_SEARCH_ENABLED`: 是否启用 Agent 联网研究链路。
- `WCPA_SEARCH_PROVIDER`: Agent 联网搜索服务；当前产品链路使用 `firecrawl`。
- `WCPA_FIRECRAWL_API_KEY`: 可选 Firecrawl API Key；留空时后端会先尝试 Firecrawl Keyless，若服务返回 401/403 或超时则清晰降级。
- `WCPA_RAG_ENABLED`: 是否启用 RAG 持久化与召回。
- `WCPA_RAG_VECTOR_BACKEND`: RAG 向量后端；当前使用 PostgreSQL + `pgvector`。
- `WCPA_EMBEDDING_PROVIDER` / `WCPA_EMBEDDING_MODEL` / `WCPA_EMBEDDING_API_KEY`: 可选 Embedding 配置；未配置时退化为 SQL + 关键词召回。

## Agent 对话

前端提供右侧抽屉式 Agent 对话入口。用户在浏览器中填写自己的模型 API Key，默认仅保存在当前浏览器会话；发起对话时 Key 会临时发送到后端，由 `/api/agents/chat/stream` 代理调用 OpenAI-compatible 模型服务，服务端不持久化保存该 Key。

联网搜索不是 DeepSeek API 自带能力，而是后端 `ResearchAnswerEngine` 自建研究链路：本地赛程校验、Firecrawl 搜索/抓取、来源相关性过滤、RAG 召回、带引用生成和质量评分。Firecrawl 密钥是可选配置；未配置密钥时会先尝试 Keyless，搜索服务不可用时 Agent 会明确降级到本地数据模式，不会伪装成已经联网。

### 已完赛比赛复盘

首页对已结束比赛发起分析时，会使用独立的 `post_match_report` 意图：

- 查询词包含英文队名、最终比分、比赛阶段以及 `match report`、`goals`、`reaction` 等赛后关键词，不会继续搜索伤停、首发预测或赛前预览。
- 搜索成功后继续读取高相关报道正文；单次查询或正文抓取失败不会清空已经取得的其他来源。
- 本地赛程只能确认比赛身份、最终比分、场馆和晋级关系。进球时间、球员、换人、射门统计和战术事件必须由引用来源明确支持。
- 赛后模式不会携带胜平负概率和模型权重，也不会因为问题中出现“比分”或“胜负手”而误入赛前预测分支。
- 质量门禁会拒绝用“常规时间概率”“期望进球”或模型组件权重冒充比赛复盘；首次回答不合格时会自动重写，再次失败则返回明确的安全降级结果。
- 没有可用战报时只展示本地可确认赛果；已取得报道但模型整理不可用时展示带引用的原始证据摘录，不根据比分虚构比赛过程。
- 只有比赛数据包含精确开球时刻时，页面和环境分析才会展示小时级时间与开球天气，避免把日期占位的 `00:00` 当作真实开球时间。

开发后端请保留 `--reload` 参数，避免前端已经更新而 8000 端口仍运行旧研究逻辑：

```powershell
$env:PYTHONPATH = "backend"
python -m uvicorn wcpa.api.server:app --reload --host 127.0.0.1 --port 8000
```

## 数据与提交策略

仓库提交源码、配置、样例数据和必要的前端静态资源。以下内容默认不提交：

- `.env`
- `outputs/`
- `data/cache/`
- `data/knowledge/`
- `frontend/dist/`
- `docs/`
- `开源数据/`

这样可以避免把本地密钥、抓取缓存、构建产物和内部文档误传到公开仓库。

## 项目状态

当前版本适合用于本地演示、继续开发和验证整体架构。预测结果依赖当前数据质量、模型权重和规则配置，不应被视为正式投注、投资或任何现实决策建议。
