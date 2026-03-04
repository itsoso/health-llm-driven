# Health Management OpenClaw Skills

三个 OpenClaw Skills，让你在任何 OpenClaw 连接的渠道（Telegram、Discord、微信等）管理健康数据。

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
          "HEALTH_API_URL": "https://your-health-api.com/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      },
      "health-record": {
        "env": {
          "HEALTH_API_URL": "https://your-health-api.com/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      },
      "health-analysis": {
        "env": {
          "HEALTH_API_URL": "https://your-health-api.com/api/v1",
          "HEALTH_API_TOKEN": "your-jwt-token"
        }
      }
    }
  }
}
```

## 使用示例

- "查一下我今天的步数"
- "最近一周的睡眠数据"
- "记录喝水250ml"
- "体重72公斤"
- "血压120/80"
- "俯卧撑打卡30个"
- "分析我的健康趋势"
- "今天的健康建议"
