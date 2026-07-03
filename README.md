# World Cup Oracle

> 理性模型与象征推理融合的世界杯冠军预测 Agent

World Cup Oracle 是一个融合 **理性预测 × 叙事感知 × 象征推理** 三轨道的世界杯冠军预测系统。通过多 Agent 辩论机制推演小组赛到决赛完整赛程，预测冠军并以可视化方式解释推理过程。

## 技术栈

| 层级 | 技术选择 |
| --- | --- |
| 后端 | Python 3.10+ / FastAPI / Pydantic v2 / NumPy |
| 前端 | React 19 + Vite + TypeScript + Tailwind CSS + ECharts |
| 数据格式 | YAML (配置) / JSON (数据 fixtures & artifacts) |
| 包管理 | pip (pyproject.toml) / npm |
| 环境管理 | Conda |

## 环境准备

### Python 环境

项目使用 Conda 环境 `llm_eval`：

```bash
# 方式一：激活 conda 环境
conda activate llm_eval

# 方式二：直接使用完整路径（推荐，避免环境切换问题）
set PYTHON=C:\Users\CJB20\anaconda3\envs\llm_eval\python.exe
```

安装 Python 依赖：

```bash
C:\Users\CJB20\anaconda3\envs\llm_eval\python.exe -m pip install -e ".[dev]"
```

### 前端环境

> **注意：** 在 Windows PowerShell 中，请使用 `npm.cmd` 而非 `npm`，否则可能无法正确执行。

```bash
cd frontend
npm.cmd install
```

## 快速开始

### 1. 运行预测流水线

```bash
# 使用 conda 环境
conda activate llm_eval
python -m scripts.run_prediction --seed 42

# 或使用完整路径
C:\Users\CJB20\anaconda3\envs\llm_eval\python.exe -m scripts.run_prediction --seed 42
```

预测结果将输出到 `outputs/predictions/` 和 `outputs/reports/`。

### 2. 启动后端 API

```bash
conda activate llm_eval
python -m uvicorn wcpa.api.server:app --reload --host 127.0.0.1 --port 8000

# 或使用完整路径
C:\Users\CJB20\anaconda3\envs\llm_eval\python.exe -m uvicorn wcpa.api.server:app --reload --host 127.0.0.1 --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm.cmd run dev
```

前端默认运行在 `http://localhost:5173`。

## 目录结构

```text
world-cup-predictor-agent/
├── README.md                    # 本文件
├── pyproject.toml               # Python 项目配置（包名 wcpa，映射到 backend/）
├── .env.example                 # 环境变量模板
├── .gitignore
├── 世界杯冠军预测Agent项目提示词.md  # 项目设计提示词文档
│
├── config/                      # 配置文件（赛制、权重、规则等）
│   ├── app.yml                  # 应用全局配置
│   ├── tournament-2026.yml      # 2026 世界杯赛制
│   ├── model-weights.yml        # 球队评分权重 & 三轨融合权重
│   ├── narrative-rules.yml      # 叙事感知规则
│   ├── symbolic-rules.yml       # 象征推理规则（塔罗/卦象/星象）
│   ├── debate-rules.yml         # 多 Agent 辩论规则
│   ├── simulation.yml           # 蒙特卡洛模拟参数
│   └── data-sources.yml         # 数据源配置
│
├── data/
│   ├── raw/                     # 原始采集数据（算法不直接读取）
│   ├── normalized/              # 清洗后的标准数据
│   ├── fixtures/                # 示例数据（MVP 使用）
│   │   ├── teams.sample.json    # 16 支球队数据
│   │   ├── matches.sample.json  # 24 场小组赛
│   │   ├── narratives.sample.json # 16 队叙事画像
│   │   ├── tarot-cards.sample.json  # 塔罗牌义
│   │   ├── iching.sample.json   # 易经卦象
│   │   └── astrology-rules.sample.json # 星象规则
│   ├── cache/                   # 外部 API 缓存
│   └── artifacts/               # 中间结构化产物
│
├── backend/                     # Python 后端代码（包名 wcpa）
│   ├── __init__.py
│   ├── shared/                  # 通用类型、常量、工具
│   ├── schemas/                 # Pydantic 模型
│   ├── data/                    # 数据采集与标准化
│   ├── features/                # 特征构造
│   ├── prediction/              # 理性预测（Poisson/Elo/评分）
│   ├── simulation/              # 赛程推演（小组/淘汰赛/蒙特卡洛）
│   ├── narrative/               # 叙事感知引擎
│   ├── symbolic/                # 象征推理引擎（塔罗/卦象/星象）
│   ├── debate/                  # 多 Agent 辩论与裁决
│   ├── agents/                  # Agent 编排
│   ├── reasoning/               # 推理链与解释生成
│   ├── report/                  # 报告生成
│   └── api/                     # FastAPI 服务
│
├── scripts/                     # 命令行入口脚本
│   └── run_prediction.py        # 预测流水线入口
│
├── frontend/                    # React 前端（Vite + TS）
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
│
├── outputs/                     # 运行结果输出
│   ├── predictions/             # 预测 JSON
│   ├── reports/                 # Markdown/HTML 报告
│   └── screenshots/             # 页面截图
│
└── docs/                        # 项目文档
    ├── README.md                # 文档索引
    ├── architecture.md          # 分层架构说明
    ├── data-contracts.md        # 数据 schema 与契约
    ├── product-requirements.md  # 产品需求
    ├── data-sources.md          # 数据源说明
    ├── model-design.md          # 模型设计
    ├── agent-workflow.md        # Agent 工作流
    ├── frontend-design.md       # 前端设计
    └── evaluation.md             # 验收标准与测试
```

## 核心概念

- **三轨道融合**：理性预测（默认 70%）+ 叙事感知（20%）+ 象征推理（10%），支持专业/平衡/爆冷/娱乐四种模式
- **多 Agent 辩论**：Data Analyst、Tactical Analyst、Narrative、Tarot、I-Ching、Astrology Agent 各自给出观点，由 Judge Agent 裁决
- **可复现性**：同一份输入数据、同一套参数和同一随机种子得到一致输出
- **可解释性**：每场比赛都有预测比分、胜平负概率、置信度、爆冷指数和推理依据

## 配置说明

所有可变参数位于 `config/` 目录，详见 [docs/](docs/) 下各文档。

## 许可证

MIT
