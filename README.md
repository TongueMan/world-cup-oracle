# World Cup Oracle

World Cup Oracle 是一个面向 2026 世界杯的冠军预测与赛程数据 Agent 项目。项目目标不是只给出一个“冠军名单”，而是把赛程数据、球队基础强度、叙事因素、象征推理和多 Agent 辩论组织成一套可运行、可解释、可扩展的预测系统。

当前仓库已经完成了前后端骨架、预测流水线雏形、Bing 体育数据同步、PostgreSQL 持久化、React 数据看板和 Docker Compose 本地部署。项目仍处在迭代阶段，部分 Agent 编排和真实数据校验策略还会继续增强。

## 当前进展

已完成或基本可用：

- FastAPI 后端服务，提供健康检查、预测、赛程、球队、小组、淘汰赛、知识库、Agent 等 API 路由。
- 48 队世界杯预测引擎雏形，支持小组赛、淘汰赛、冠军概率、比赛预测和推理产物输出。
- 基础预测模型，包括球队强度特征、Poisson/比分模型、置信度和蒙特卡洛模拟。
- 叙事与象征推理模块，包括 narrative、tarot、iching、astrology、upset signal 等独立组件。
- Agent 辩论与评审骨架，包括数据、预测、叙事、象征、推理和 judge 相关模块。
- Bing 体育世界杯数据同步，包含赛程、淘汰赛、排名、球员统计等结构化数据接口。
- PostgreSQL 仓储层，用于保存同步数据、预测缓存和运行产物。
- React + Vite + TypeScript 前端，当前重点是世界杯赛程/赛果指挥舱：比赛、淘汰赛、排名、统计信息和同步状态。
- Docker Compose，包含 Postgres、API、前端 Nginx 三个服务。
- 单元测试和集成测试目录，覆盖预测、赛程、API、schema、符号稳定性等核心路径。

仍在完善：

- 多 Agent 工作流的完整自动编排。
- LLM Agent 的提示词、工具调用和结果评审策略。
- 真实数据源的稳定性、异常恢复和数据质量门禁。
- 前端从“赛程数据看板”扩展到完整“预测解释与 Agent 辩论工作台”。

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
    agents/             # Agent 接口、工具与辩论相关逻辑
    api/                # FastAPI 应用与路由
    data/               # 数据源、标准化、仓储层
    debate/             # Agent 观点汇总与 judge
    features/           # 球队特征构建
    narrative/          # 叙事评分
    prediction/         # 比赛预测模型
    reasoning/          # 解释与推理轨迹
    simulation/         # 小组赛、淘汰赛、冠军模拟
    symbolic/           # 塔罗、易经、占星等象征信号
    worldcup/           # 世界杯赛程数据服务
config/                 # 模型权重、规则、数据源、赛事配置
data/
  fixtures/             # 样例数据
  normalized/           # 标准化样例和当前真实数据快照
frontend/               # React 前端
```

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

也可以直接启动完整本地环境：

```bash
docker compose up --build
```

默认服务：

- API: `http://localhost:8000`
- 前端: `http://localhost:8080`
- PostgreSQL: `localhost:5432`

## 常用命令

运行预测流水线：

```powershell
$env:PYTHONPATH = "backend"
python -m scripts.run_prediction --seed 42
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
python -m pytest
```

前端构建：

```powershell
cd frontend
npm.cmd run build
```

## 环境变量

`.env.example` 保留了项目需要的变量名和安全默认值。真实密钥只应放在本地 `.env` 中，不要提交到仓库。

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
