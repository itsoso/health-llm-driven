# Health Management OpenClaw Skills

一组 OpenClaw Skills，让你在任何 OpenClaw 连接的渠道（Telegram、Discord、微信等）管理健康数据。

## Skills 列表

### 核心 (data in/out)
| Skill | 功能 |
|-------|------|
| `health-query` | 查询健康数据（步数、心率、睡眠、体重、血压、环境、病症、计划、异常、补剂、情绪等） |
| `health-record` | 记录健康数据（饮水、体重、血压、打卡、饮食、补剂、病症、排便、情绪、提醒等） |
| `health-data-summary` | 综合查询 — Digital Twin 快照、Safety 告警、长期趋势、Orchestrator 多专家分析 |
| `multi-source-integration` | 多源数据整合 — Garmin 分钟级时序 + CGM + 化验 + 基因整合时间线 |

### 分析 / 诊断
| Skill | 功能 |
|-------|------|
| `health-analysis` | AI 健康分析、每日建议、趋势预测、恢复状态 |
| `spo2-analysis` | **夜间血氧 SpO2 时间序列** — 逐分钟曲线、ODI、低氧事件、OSAHS 筛查 |
| `sleep-deep-analysis` | 深度睡眠分析 — 睡眠架构、HRV 恢复、睡眠债 |
| `chronic-risk-assessment` | 慢病风险 — Framingham 心血管、代谢综合征、糖尿病 |
| `exercise-recovery` | 运动恢复 — ACWR 训练负荷、readiness 评分 |
| `genetic-analysis` | 基因检测数据查询与分析（MTHFR / APOE / FTO 等） |

### 专项管理
| Skill | 功能 |
|-------|------|
| `medication-tracker` | 用药跟踪 — 记录服药、依从性检查、药物信息 |
| `allergy-symptom-tracker` | 过敏症状跟踪（眼痒、喷嚏、鼻塞、皮疹等） |
| `rhinitis-tracker` | 鼻炎专项跟踪（症状分级、环境关联、用药依从） |
| `nutrition-advisor` | 个性化营养建议（基于 TDEE、今日摄入、运动、目标） |
| `supplement-advisor` | 科学补剂建议（基于睡眠、压力、运动模式） |
| `environment-health` | 环境健康（天气、AQI、紫外线、户外活动评估） |

### 计划 / 动作
| Skill | 功能 |
|-------|------|
| `personal-plan` | 生成并保存个性化健康计划（训练、饮食、恢复、复查） |
| `weekly-planner` | 周计划管理 — 创建、跟踪、完成 |
| `reminder-setter` | 健康提醒设置（服药、复查、运动、饮水） |
| `action-card-manager` | 首页行动卡片管理（创建、完成、归档） |
| `workout-coach` | 运动指导 — 前中后全流程 |

### 家庭
| Skill | 功能 |
|-------|------|
| `family-health` | 家庭健康管理 — 成员病历、用药、复查日历 |

## 安装

### 全部安装（推荐）

```bash
# 复制所有 skill 到 OpenClaw
cp -R openclaw-skills/*/ ~/.openclaw/skills/
```

### 按需安装

```bash
# 只装核心 + SpO2 + 睡眠深度分析
cp -R openclaw-skills/{health-query,health-record,health-analysis,spo2-analysis,sleep-deep-analysis} ~/.openclaw/skills/
```

## 同步到 backend/skills

这套分发包由仓库根目录的 `scripts/sync-skills.sh` 从 `backend/skills/` 生成。
当后端加/改 skill 后，跑一次即可：

```bash
./scripts/sync-skills.sh          # 仅报告差异
./scripts/sync-skills.sh --apply  # 同步缺失的 skill
```

已存在于 `openclaw-skills/` 的 skill 不会被覆盖（它们可能已有独立演进）；
如需强制重置某个 skill：`./scripts/sync-skills.sh --force <skill-name>`。

## 配置

在 `~/.openclaw/openclaw.json` 中给每个 skill 注入环境变量。示例（核心三个 + SpO2）：

```json
{
  "skills": {
    "entries": {
      "health-query": {
        "env": {
          "HEALTH_API_URL": "https://health.executor.life/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      },
      "health-record": {
        "env": {
          "HEALTH_API_URL": "https://health.executor.life/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      },
      "health-analysis": {
        "env": {
          "HEALTH_API_URL": "https://health.executor.life/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      },
      "spo2-analysis": {
        "env": {
          "HEALTH_API_URL": "https://health.executor.life/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      }
    }
  }
}
```

**所有 skill 共用同一套 `HEALTH_API_URL` + `HEALTH_API_TOKEN`**，
其他 skill 照抄即可，只改 key 名。

## 服务器部署

```bash
# 复制到服务器
scp -r openclaw-skills/* root@39.98.206.178:~/.openclaw/skills/

# SSH 到服务器验证
ssh root@39.98.206.178 "ls ~/.openclaw/skills/"
```

## 使用示例

```
# 查询
"查一下我今天的步数"
"最近一周的睡眠数据"
"我的心率变化趋势"

# 记录
"记录喝水250ml"
"体重72公斤"
"血压120/80"
"俯卧撑打卡30个"
"午餐吃了一碗米饭一份鸡胸肉"

# 分析
"分析我的健康趋势"
"今天的健康建议"
"我有哪些健康风险？"
```

---

## SKILL.md 编写指南

OpenClaw Skill 通过 `SKILL.md` 文件定义。以下是创建新 Skill 的方法。

### 文件结构

每个 Skill 是一个独立目录，包含一个 `SKILL.md` 文件：

```
~/.openclaw/skills/
├── health-query/
│   └── SKILL.md
├── health-record/
│   └── SKILL.md
└── health-analysis/
    └── SKILL.md
```

### SKILL.md 格式

```markdown
---
name: skill-name
description: 简要描述这个 Skill 的功能
requires:
  env:
    - ENV_VAR_1
    - ENV_VAR_2
---

在这里编写 Skill 的指令内容（Markdown 格式）。

## 认证方式
- URL: ${ENV_VAR_1}
- Header: `Authorization: Bearer ${ENV_VAR_2}`

## 可用端点

### 端点名称
​```bash
curl -s -H "Authorization: Bearer ${ENV_VAR_2}" "${ENV_VAR_1}/endpoint"
​```
返回说明...

## 响应规则
- 用中文回复
- 包含单位
```

### YAML Frontmatter 字段

| 字段 | 必填 | 说明 |
|------|:---:|------|
| `name` | ✅ | Skill 唯一标识，与目录名一致 |
| `description` | ✅ | 功能描述，OpenClaw 用来决定何时调用此 Skill |
| `requires.env` | ❌ | 需要的环境变量列表，在 `openclaw.json` 中配置 |

### 编写要点

1. **Description 要精准**：OpenClaw 根据 description 判断用户意图是否匹配此 Skill，写清楚能做什么
2. **用 curl 定义操作**：Skill 中通过 curl 命令描述 API 调用，OpenClaw 会自动执行
3. **环境变量用 `${VAR}`**：在 curl 命令中引用环境变量，运行时自动替换
4. **响应规则很重要**：告诉 AI 如何格式化输出（语言、单位、高亮等）
5. **一个 Skill 一个职责**：查询、记录、分析分开，避免单个 Skill 过于庞大

### 创建新 Skill 的步骤

```bash
# 1. 创建目录
mkdir -p ~/.openclaw/skills/my-new-skill

# 2. 编写 SKILL.md
cat > ~/.openclaw/skills/my-new-skill/SKILL.md << 'EOF'
---
name: my-new-skill
description: 描述这个 Skill 的功能
requires:
  env:
    - API_URL
    - API_TOKEN
---

指令内容...
EOF

# 3. 在 openclaw.json 中注册
# 添加 env 配置到 skills.entries.my-new-skill

# 4. 重启 OpenClaw 生效
```

### 示例：最小化 Skill

```markdown
---
name: weather
description: Query current weather for a city
requires:
  env:
    - WEATHER_API_KEY
---

Use the weather API to answer weather questions.

## Endpoint
​```bash
curl -s "https://api.weather.com/v1/current?key=${WEATHER_API_KEY}&q={city}"
​```

Always respond in Chinese with temperature in Celsius.
```
