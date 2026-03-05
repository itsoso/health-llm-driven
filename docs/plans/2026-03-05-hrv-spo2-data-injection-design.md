# HRV + SpO2 数据盲区补全 — 两通道同步升级

**日期**: 2026-03-05
**状态**: 已批准

## 背景

GarminData 模型已有 `hrv`, `hrv_status`, `hrv_7day_avg`, `spo2_avg`, `spo2_min`, `spo2_max` 字段，Garmin 同步时已写入数据库。但 chat_service.py 的 `_build_health_context` 未注入这些数据，OpenClaw 的 health-query Skill 也没有对应查询端点。AI 对话完全"看不到"用户的 HRV 和 SpO2 数据。

## 改动范围

### 1. 健康助理对话上下文增强

**文件**: `backend/app/services/chat_service.py`

**改动点**:
- 最新 Garmin 数据注入（~第252行）补充 HRV 三字段和 SpO2 三字段
- 7天趋势新增 HRV 趋势段落（每日值+状态、均值/最高/最低、趋势方向、low天数）
- 7天趋势新增 SpO2 趋势段落（每日均值/最低、总均值、最低日、低于95%天数）
- 系统提示规则增加：当 HRV status=low 或 SpO2 最低<95% 时主动提醒

**预计**: ~50 行新增，~200 tokens 额外上下文

### 2. 后端 API 新增端点

**文件**: `backend/app/services/garmin_analysis.py`, `backend/app/api/garmin_analysis.py`

**新增**:
- `GET /garmin-analysis/me/hrv?days=7` — HRV 趋势分析（latest/average/min/max/trend/low_days/daily_data）
- `GET /garmin-analysis/me/spo2?days=7` — SpO2 趋势分析（latest/average/min/below_95_days/daily_data）

遵循现有 `analyze_heart_rate` 的代码模式。

### 3. health-query Skill 模板更新

**文件**: `frontend/src/app/skills/page.tsx`

- 在 health-query 模板中新增 HRV 和 SpO2 两个 curl 端点
- toolCount 从 13 改为 15
- 描述更新加入 "HRV、SpO2"

### 4. 部署

1. 部署后端（新 API 端点生效）
2. 部署前端（Skill 模板更新）
3. 重新安装 health-query Skill 到 OpenClaw 服务器
4. 重启 Gateway

## 验证

1. 健康助理模式：问"我的HRV怎么样"，AI 能直接给出精准分析
2. 健康助理模式：当 HRV 低或 SpO2 低时，AI 主动在回答中提醒
3. OpenClaw 模式：问"查看我的血氧数据"，通过 Skill 调用 API 返回结果
4. 新 API 端点可直接测试：`/garmin-analysis/me/hrv` 和 `/garmin-analysis/me/spo2`
