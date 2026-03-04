# Health Management OpenClaw Skills

三个 OpenClaw Skills，让你在任何 OpenClaw 连接的渠道（Telegram、Discord、微信等）管理健康数据。

## Skills 列表

| Skill | 功能 | 工具数 |
|-------|------|:------:|
| `health-query` | 查询健康数据（步数、心率、睡眠、体重、血压等） | 13 |
| `health-record` | 记录健康数据（饮水、体重、血压、打卡、饮食） | 5 |
| `health-analysis` | 健康分析与建议（趋势、风险、评分） | 6 |

## 安装

将 skill 目录复制到 OpenClaw 的 skills 目录：

```bash
cp -r health-query health-record health-analysis ~/.openclaw/skills/
```

## 配置

在 `~/.openclaw/openclaw.json` 中添加：

```json
{
  "skills": {
    "entries": {
      "health-query": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      },
      "health-record": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      },
      "health-analysis": {
        "env": {
          "HEALTH_API_URL": "https://health-api.executor.life/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      }
    }
  }
}
```

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
