# 复元 Reva · Personal Health OS

> 将分散的健康数据转化为可执行的日常行动，并持续验证这些行动对个人是否有效。

Reva 是一个 AI 驱动的个人健康管理与执行系统。它整合体检、可穿戴设备、症状、饮食、运动、用药与补剂记录，结合安全规则和个人状态，帮助用户选择当前值得做的行动、完成记录，并通过复查与趋势回顾评估结果。

产品优先服务于 35–55 岁、工作强度高、存在早期代谢风险或恢复问题的人群：已有健康数据和改善意愿，但缺少持续执行的时间与精力。

[产品能力](#产品能力) · [系统与目录](#系统与目录) · [本地开发](#本地开发) · [测试与验证](#测试与验证) · [部署与发布](#部署与发布) · [文档导航](#文档导航)

## 产品理念

健康管理的价值来自持续执行和结果反馈。Reva 围绕以下闭环组织数据、建议与行动：

```text
体检 / 可穿戴设备 / 症状 / 用药 / 补剂 / 行为记录
  → 数字健康孪生：整理个人状态与证据
  → 安全检查：识别风险和需要人工介入的情况
  → 行动排序：选择当前值得执行的事项
  → 健康日程：通过 Mobile / Watch / Mac 辅助执行
  → 执行记录：保留完成情况与反馈
  → 复查与结果回顾：比较变化、说明不确定性
  → 下一轮行动
```

长期目标是形成可追溯的个人行动与结果账本：建议了什么、实际执行了什么、哪些结果得到验证，以及证据有哪些局限。趋势变化与复查结果需要结合噪声、缺失数据和其他影响因素解释，不能直接视为因果证明。

## 产品能力

下表列出仓库中的主要实现入口。代码存在不代表所有设备、外部服务和生产流程均已完成验收；具体边界与成熟度见[产品地图](docs/system-map/product-map.md)及各功能的 [Dossier](docs/dossiers/)。

| 能力 | 用途 | 实现入口 |
|---|---|---|
| 数字健康孪生 | 为界面和 Agent 提供共享的个人健康语义状态 | [backend/app/twin/](backend/app/twin/) |
| Agent 编排 | 路由专科分析、工具调用与结果汇总 | [backend/app/orchestrator/](backend/app/orchestrator/) |
| 安全守护 | 对生命体征、化验、药物与补剂相互作用、药物基因组、血糖、症状和训练负荷执行规则检查 | [backend/app/agents/safety_guardian/](backend/app/agents/safety_guardian/) |
| 健康日程与行动排序 | 汇总日程，并结合可执行性、可验证性、信心、执行成本与安全等级排序 | [agenda_service.py](backend/app/services/agenda_service.py)、[action_ranker.py](backend/app/services/action_ranker.py) |
| 干预周期与结果回顾 | 管理基线、目标、复查和指标变化，给出考虑噪声的结果状态 | [intervention_cycle_service.py](backend/app/services/intervention_cycle_service.py) |
| 体检与生物标志物 | 将体检信息整理为标准化观测数据 | [backend/app/biomarkers/](backend/app/biomarkers/)、[biomarker_service.py](backend/app/services/biomarker_service.py) |
| 长寿指标 | 基于血液检测计算 PhenoAge，并保留适用范围和解释边界 | [phenoage.py](backend/app/services/phenoage.py) |
| 多端执行 | 展示当前行动、完成记录、导入资料和查看分析证据 | [mobile/](mobile/)、[apps/watch/](apps/watch/)、[apps/mac/](apps/mac/) |

### 各端职责

| 端 | 主要职责 |
|---|---|
| Mobile | 日常入口：查看今日状态与行动、记录健康数据、完成用药与补剂打卡、跟踪干预周期 |
| Apple Watch | 手腕上的执行入口：查看重点行动、到期事项与数据新鲜度，提供快捷操作 |
| Mac | 桌面工作台：资料导入、对话、任务管理、证据与执行轨迹查看 |
| Web | 管理、历史数据与辅助视图 |
| Backend | 健康状态、安全规则、行动排序、持久化与审计的权威来源 |

## 安全边界

Reva 用于个人健康管理。它不替代医生、诊断设备、处方决策或急救分诊。

- 不开具处方，不自主调整药物剂量。
- 不以模型回答替代诊断，不对危险症状给出“没有问题”的结论。
- 数据不足或证据较弱时，明确说明不确定性。
- 高风险路径需要安全规则、人工审核或临床随访。
- 健康数据读写必须按认证用户隔离；日志、公开分享和通知遵循隐私约束。

详细边界见[健康理念](docs/HEALTH_WORLDVIEW.md)、[安全治理](docs/governance/security.md)和[隐私治理](docs/governance/privacy.md)。

## 系统与目录

```text
Mobile / Watch / Mac / Web
            ↓
FastAPI API · 认证 · 审计
            ↓
数字健康孪生 · 安全守护 · Agent 编排
健康日程 · 行动排序 · 干预周期与结果回顾
            ↓
PostgreSQL · Redis · Celery
            ↕
设备数据 / 体检资料 / 外部服务 / LLM Provider
```

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12、FastAPI、SQLAlchemy、Pydantic |
| 数据与后台任务 | PostgreSQL、Redis、Celery / Celery Beat |
| Agent 执行 | 官方 Pi Node.js runtime，Python 负责模型传输与健康工具执行 |
| 移动端 | Expo、React Native、TypeScript |
| Watch / Mac | Swift 原生客户端与 Swift Package |
| Web | Next.js、React、TypeScript |
| 模型接入 | OpenAI 兼容接口及其他已配置 Provider |

```text
backend/        API、模型、服务、Agent、受管迁移与测试
mobile/         Expo 移动端、组件与 API 客户端
apps/watch/     Watch 应用模块与测试
apps/mac/       原生 Mac 工作台
frontend/       Next.js Web 应用
mcp-server/     MCP 集成
packages/       共享包
docs/           产品、架构、治理、验证证据与历史归档
scripts/        开发检查、迁移、构建与发布辅助工具
```

架构说明见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)。追踪跨端流程从 [System Map](docs/system-map/INDEX.md) 开始；代码派生结构以[生成地图](docs/_generated/system-map.json)为准。

## 本地开发

### 环境准备

- Python 3.12。
- Node.js ≥ 22.19.0 与 npm，供 Pi runtime 和前端开发使用。
- 已启动的 PostgreSQL 与 Redis，以及独立的本地开发数据库。
- 开发 Watch / Mac 时，需要 macOS 和对应的 Xcode / Swift 工具链。

以下命令均从仓库根目录开始；每个代码块在独立终端运行。开发与新数据库行为统一使用 PostgreSQL；SQLite 仅用于显式指定的快速单测或迁移兼容验证。

### 后端

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
bash pi-runtime/install.sh

# 仅首次配置；已有 .env 时保留现有文件。
cp -n .env.example .env
```

启动前编辑 `backend/.env`。示例文件包含生产配置，不能原样用于本地开发：

| 配置 | 本地开发要求 |
|---|---|
| `APP_ENV` | 设置为 `development` |
| `DATABASE_URL` | 指向已创建的本地 PostgreSQL 开发库 |
| `REDIS_URL` | 指向本地 Redis，例如 `redis://localhost:6379/0` |
| `SECRET_KEY` | 使用独立随机值，至少 32 字符 |
| `LLM_PROVIDER` 与模型配置 | 填入实际使用的 Provider、模型及所需凭证；参考示例文件与配置源码 |
| 数据目录覆盖 | 移除示例中的生产路径覆盖，或改成可写的本地目录，包括 `HEALTH_RUNTIME_DATA_DIR`、`HEALTH_UPLOAD_DIR`、`HEALTH_SKILLS_CACHE_DIR` 和 `DEDAO_KBASE_REVIEW_ARTIFACT_DIR` |

配置定义见 [app/config.py](backend/app/config.py)，运行时安装与协议见 [Pi runtime 说明](backend/pi-runtime/README.md)。凭证只保存在本地配置中，不提交到仓库。

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

本地开发启动会创建 ORM 表并执行历史兼容初始化；已有数据库的受管迁移入口是 [apply_managed_migrations.py](backend/scripts/apply_managed_migrations.py)。生产环境必须使用独立迁移角色，流程见[数据库治理](docs/governance/database.md)和[部署治理](docs/governance/deploy.md)。

需要同步、通知等后台任务时，在后端虚拟环境中分别启动：

```bash
celery -A app.celery_app:celery_app worker --loglevel=info
celery -A app.celery_app:celery_app beat --loglevel=info
```

### Mobile

```bash
cd mobile
npm ci
EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo start --dev-client
```

使用开发构建与 iOS 模拟器进行日常验收。项目依赖原生模块，需要与当前依赖匹配的开发客户端；Expo Go 不能覆盖完整功能。连接其他设备或 Android 模拟器时，按环境调整后端地址。`EXPO_PUBLIC_API_URL` 未设置时使用线上默认地址，详见 [services/api.ts](mobile/services/api.ts)。

### Web

```bash
cd frontend
npm ci
cp -n .env.example .env.local
npm run dev
```

在 `frontend/.env.local` 设置 `BACKEND_URL=http://localhost:8000`。本地页面默认位于 `http://localhost:3000`。

### Mac 与 Watch

```bash
# Mac：测试并启动桌面客户端
cd apps/mac
swift test
swift run HealthAgentMac
```

```bash
# Watch：运行 Swift Package 测试
cd apps/watch
swift test
```

Mac 的功能边界、打包与签名说明见 [apps/mac/README.md](apps/mac/README.md)。Watch 的 Swift Package 测试不能替代 watchOS 应用验收。

## 测试与验证

按修改范围选择检查。以下是常用入口，不能替代发布所需的集成验证和精确 revision CI。

| 范围 | 命令（在对应目录执行） |
|---|---|
| 后端 | `python -m pip install -r requirements-dev.txt`，然后 `python -m pytest tests/<相关测试文件>.py` |
| Mobile | `npx tsc --noEmit`、`npm test -- --runInBand` |
| Web | `npx tsc --noEmit`、`npm test`、`npm run lint` |
| Mac / Watch | `swift test` |
| 仓库格式 | 根目录执行 `git diff --check` |
| 地图与文档漂移 | 根目录执行 `./scripts/system-map-check.sh` |

后端测试使用已激活的虚拟环境。约束、并发、JSONB、时区和方言等数据库行为必须有 PostgreSQL 证据；`TEST_DATABASE_URL` 应指向独立测试库，库名包含 `test`。接口变更需要同步验证后端与客户端类型。

详细要求见[测试治理](docs/governance/testing.md)与[数据库治理](docs/governance/database.md)。

## 部署与发布

部署前需满足项目 CI-mode 集成闸、目标主干精确 revision 的真实 CI，以及对应安全和发布 Gate。部署使用干净、已验证的目标 revision；部署成功后仍需完成线上验证并保留回执。

| 目标 | 当前入口 |
|---|---|
| Backend / Web | 根目录 `deploy.sh`；操作步骤、参数与恢复流程见[部署治理](docs/governance/deploy.md) |
| Mobile OTA | [trusted-ota.yml](.github/workflows/trusted-ota.yml)：同一当前 main 精确绿色 SHA 先 `validate` 后 `publish`，后端须已部署该 SHA |
| 可扫码安装的 iOS 包 | [scripts/mobile-local-qr.sh](scripts/mobile-local-qr.sh) |
| 原生依赖、签名、权限或商店元数据变更 | 按对应原生发布流程与审核 Gate 执行 |
| Mac 正式分发 | 按 Mac 发布流程完成签名、公证与验收；本地打包说明见 [Mac README](apps/mac/README.md) |

本机 `mobile-ota.sh` 与 OTA rollback 发布入口已冻结。失败时按治理文档保留原回执并恢复，不能通过重发绕过 Gate。

## 文档导航

| 想了解什么 | 阅读入口 |
|---|---|
| 产品定位与需求准入 | [产品治理规范](docs/specs/reva-product-governance-spec.md) |
| 产品定义与行动闭环 | [Personal Health OS PRD](docs/prd/reva-personal-health-os-prd.md)、[健康行动产品设计](docs/prd/2026-06-16-health-leverage-action-os-pdd.md) |
| 当前能力、多端关系与系统流程 | [System Map](docs/system-map/INDEX.md)、[产品地图](docs/system-map/product-map.md)、[架构说明](docs/ARCHITECTURE.md) |
| 从需求到上线 | [产品流水线契约](docs/specs/product-pipeline-contract.md)、[在途功能与证据](docs/dossiers/) |
| 健康理念与模型验证 | [HEALTH_WORLDVIEW.md](docs/HEALTH_WORLDVIEW.md)、[HARNESS.md](docs/HARNESS.md) |
| 安全、隐私、测试与部署 | [治理文档目录](docs/governance/) |
| 仓库研发与 Agent 规则 | [AGENTS.md](AGENTS.md) |
| 历史报告与临时说明 | [归档目录](docs/archive/) |

根目录保留入口、配置、依赖清单与部署脚本。新增产品、架构和规划文档放在 `docs/`，一次性历史报告放在 `docs/archive/`。

## 下一阶段的产品验证

产品价值需要通过真实使用与持续反馈验证。下一阶段关注小规模付费人群中的体检导入、8–12 周代谢或恢复周期、日常行动完成率、复查完成情况、考虑噪声的指标变化、安全与人工审核成本，以及续费或推荐意愿。

这些是待验证的产品目标。对个人结果的描述必须同时说明执行记录、观测变化与证据的置信边界。
