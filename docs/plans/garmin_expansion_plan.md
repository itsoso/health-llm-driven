# Garmin 数据扩展计划 (2026-04-24 起草，2026-04-24 重排 v2)

Owner: itsoso

**核心原则（用户明确）：数据第一，分析第二。**
先把 Garmin 能吐出的全部维度落到数据库里（即便没立刻用到），再在完整数据上做分析。这样数据立即开始累积，做分析时有历史样本可验，且分析逻辑迭代不影响数据积累。

**最终目标**：在完整数据基础上定位"夜间血氧饱和度波动的根因"，并结合用户在用的药物（如异丙托溴铵）、补剂、运动给出可操作的改善建议。

## 总体架构

```
P1a: 全面数据采集层 (Garmin 所有能拿的数据) ← 数据立刻开始累积
        ↓
P1b: 夜间 SpO2 根因分析 + 行为关联 (基于 P1a 数据) ← 分析器消费完整数据
        ↓
P2+:  其他 specialist 集成 (Recovery / Movement / Fuel / Longitudinal)
```

- **P1a 是基建**：dumb pipes，只做采集和存储，没有业务解读
- **P1b 是应用**：在 P1a 之上做"为什么昨晚氧降"的分析 + 行为建议
- **P2+ 是扩散**：让同一套数据反哺现有 specialist

## 原则

- **数据先于分析**：每加一条数据维度，都先验证采集落盘成功，再考虑怎么用它
- **每个 Phase 独立部署**：一个 Phase 包含 migration + collector + model + schema + api + 测试 + 一个集成点
- **向后兼容**：所有新字段 `nullable=True`，不破坏老数据
- **rollback 可行**：migration 配 rollback.sql；specialist 集成用 feature flag
- **时间序列统一表模型**：夜间逐分钟数据用 `(user_id, night_date, ts, metric, value)` 长表，不每种指标一张表
- **collector 失败不阻塞同步**：新 endpoint 失败只记 warning

---

## Phase 1a — 全面数据采集层 (基础数据，最高优先)

**目标**：把 `garminconnect` 社区库里**所有**能拿到的数据完整采集并落库。不做分析、不改 specialist、不建 UI。只确保"同步一次后库里什么都有了"。

### 覆盖维度（一次做完）

#### 时间序列（夜间 / 逐分钟）— 写入 `nightly_readings` 统一长表

| metric | 来源 | 用途 |
|---|---|---|
| `spo2` | `get_spo2_data` → `spo2ValuesArray` | SpO2 根因分析本体 |
| `respiration` | `get_respiration_data` → `respirationValuesArray` | 阻塞事件识别 |
| `hr` | `get_heart_rates` → `heartRateValues`（当前丢弃） | 代偿性 HR 升高证据 |
| `hrv` | `get_hrv_data` → `hrvReadings` | 自主神经状态 |
| `sleep_stage` | `get_sleep_data` → `sleepLevels` | REM vs NREM 期氧降 |
| `stress` | `get_stress_data` | 应激分析（也服务 MentalHealthCompanion） |

#### 日级字段（扩展 `garmin_data` 表）

| 字段 | 来源 | 用途 |
|---|---|---|
| `training_readiness_score` (int) | `get_training_readiness` | 和本系统 readiness 交叉验证 |
| `training_readiness_level` (str) | 同上 | |
| `training_readiness_factors` (JSONB) | 同上 | |
| `training_status` (str) | `get_training_status` | productive/detraining/overreaching |
| `training_status_feedback` (text) | 同上 | |
| `acute_load` (float) | 同上 | |
| `load_ratio` (float) | 同上 | ACWR |
| `endurance_score` (int) | `get_endurance_score` | 锦上添花 |
| `hill_score` (int) | `get_hill_score` | 锦上添花 |
| `race_predictions` (JSONB) | `get_race_predictions` | 5k/10k/half/full |
| `hydration_ml` (int) | `get_hydration_data` | 水合状态 |
| `vo2max_fitness_age` (int) | `get_max_metrics` | 健康年龄 |

#### 独立表

- **`body_composition_measurements`** (Index 秤): `(user_id, measured_at, weight_kg, body_fat_pct, muscle_mass_kg, bone_mass_kg, body_water_pct, visceral_fat_rating, metabolic_age, source)`
- **`workout_hr_zones`**: `(workout_id, zone_index, zone_name, lower_bpm, upper_bpm, seconds_in_zone)` + collector 调 `get_activity_hr_in_timezones(activity_id)`
- **`garmin_devices`**: `(user_id, device_id, model, last_sync_time, battery_level, last_used_time)` — 后面用于区分"HRV=0 是真低"还是"没戴表"

### 变更清单

#### 数据库迁移（6 个文件）

- `create_nightly_readings.sql` (+ rollback)
- `20260xxx_add_training_fields_to_garmin_data.sql` (+ rollback)
- `20260xxx_add_misc_garmin_fields.sql`（endurance/hill/race/hydration/fitness_age, + rollback）
- `create_body_composition_measurements.sql` (+ rollback)
- `create_workout_hr_zones.sql` (+ rollback)
- `create_garmin_devices.sql` (+ rollback)

#### Models

- `backend/app/models/nightly_reading.py`
- `backend/app/models/body_composition.py`
- `backend/app/models/workout_hr_zone.py`
- `backend/app/models/garmin_device.py`
- 扩 `backend/app/models/daily_health.py::GarminData` 字段

#### Collector (`backend/app/services/data_collection/garmin_connect.py`)

每个方法独立、失败 `warn` 不抛、返回归一化 dict/list。调用次序上，每个用户每日同步新增调用：
```
get_training_readiness / get_training_status (日级)
get_endurance_score / get_hill_score / get_race_predictions / get_hydration_data (日级)
get_spo2_data → 展开 spo2ValuesArray (时序)
get_respiration_data → 展开 respirationValuesArray (时序)
get_heart_rates → 展开 heartRateValues (时序)
get_hrv_data → 展开 hrvReadings (时序)
get_sleep_data → 展开 sleepLevels (时序)
get_stress_data → 展开逐分钟 stress (时序)
get_body_composition (若有 Index 秤)
get_activity_hr_in_timezones(activity_id) (每个新 workout)
get_devices (周级别即可)
```

所有时序数据批量 upsert 进 `nightly_readings` 时用 `ON CONFLICT (user_id, reading_ts, metric) DO UPDATE`。

#### API（只读，不做业务解读）

- `GET /garmin/nightly/me/{date}?metrics=spo2,hr,respiration` — 返回时序
- `GET /garmin/training/me/{date}` — readiness + status
- `GET /garmin/body-composition/me?days=90` — 体成分记录
- `GET /garmin/devices/me` — 设备列表
- `GET /workout/me/{id}/hr-zones` — HR zone 分布

#### Schemas

- Pydantic `NightlyReadingOut`, `BodyCompositionOut`, `TrainingReadinessOut`, `WorkoutHrZoneOut`, `GarminDeviceOut`

#### 配置

- `settings.GARMIN_TIMESERIES_RETENTION_DAYS = 365`（超过的时序数据归档 / 删除）

#### 历史回填脚本

- `backend/scripts/backfill_garmin_timeseries.py --user-id 3 --days 30`
- 先回填用户 3 最近 30 天，验证数据质量；再扩到其他用户 / 更长时间

#### 测试

- `tests/test_garmin_full_collector.py`（mock garminconnect 返回，覆盖每个新方法的解析路径）
- `tests/test_nightly_readings_api.py`
- `tests/test_garmin_training_api.py`
- `tests/test_workout_hr_zones.py`
- `tests/test_garmin_backfill_script.py`

### 验收标准

- 同步用户 3 昨夜 → `nightly_readings` 表插入 ≥1500 行（6 种 metric × 分钟粒度）
- `garmin_data` 行上 `training_readiness_score / training_status` 等字段非空（如手表支持）
- 运行回填脚本 30 天 → 数据库有 30 × 1500 ≈ 45000 条 nightly_readings 行 + 30 条 garmin_data 行带新字段
- 所有新 API 返回 200 + 正确 schema
- 某个 endpoint 对某账户 404（设备不支持）不阻塞其他数据采集
- Celery 定时同步一次 < 60s/用户（当前 <30s，新增 5-6 个 endpoint 预计 +20s）

### Rollback

- 每个 migration 配 rollback.sql，独立删表/列
- collector 新方法全独立，注释掉调用即可回退
- 无 specialist 改动，零风险

### 预估工作量

| 模块 | 行数 |
|---|---|
| Migrations (6 个 + rollback) | ~250 |
| Models (5 个) | ~200 |
| Collector (10+ 新方法 + 解析) | ~500 |
| API (5 个 endpoint) | ~200 |
| Pydantic schemas | ~150 |
| 回填脚本 | ~150 |
| 测试 | ~500 |
| **合计** | **~1950** |

约 1-1.5 周。做完后**数据立刻开始累积**。

---

## Phase 1b — 夜间 SpO2 根因分析 + 行为关联 (数据之上的应用)

**目标**：基于 P1a 已累积的完整数据，定位夜间 SpO2 波动根因，结合用药（异丙托溴铵等）、补剂、运动给出可操作建议。

### 前置条件

- P1a 已部署并累积至少 14 天数据（回填用户 3 最近 30 天即可跳过"等待"）
- `medication_logs` / `supplement_records` / `workout` / `diet_records` / `rhinitis_episodes` 已有数据（现状已满足）

### 为什么拆到 P1b

把"采集"和"分析"解耦：
- P1a 做完后数据立刻累积，不用等分析逻辑打磨完
- P1b 需要产品级决策（规则阈值、UX 表现），可能迭代几轮 → 不阻塞 P1a
- P1b 失败不影响 P1a 数据流

### 新建表

**`nocturnal_spo2_events`**（氧降事件落盘）
```sql
CREATE TABLE nocturnal_spo2_events (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  night_date DATE NOT NULL,
  start_ts TIMESTAMPTZ NOT NULL,
  end_ts TIMESTAMPTZ NOT NULL,
  duration_seconds INTEGER NOT NULL,
  min_spo2 FLOAT NOT NULL,
  drop_magnitude FLOAT NOT NULL,
  concurrent_hr_delta FLOAT,
  concurrent_respiration_rate FLOAT,
  sleep_stage VARCHAR(16),
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_nocturnal_events_user_night ON nocturnal_spo2_events(user_id, night_date);
```

### 分析服务 (`backend/app/services/sleep/nocturnal_spo2_analyzer.py`)

核心函数 `analyze_night(user_id, night_date) -> NightAnalysis`：

1. 从 `nightly_readings` 拉当晚 6 条时序（SpO2 / HR / Respiration / HRV / Sleep Stage / Stress）
2. **检测氧降事件**：滑窗识别 `SpO2 连续下降 ≥4% 持续 ≥10s`
3. 对每个事件计算：min_spo2 / duration / 同期 HR delta / 呼吸率 / 睡眠阶段
4. 计算夜间 ODI = 每小时氧减事件数
5. 写入 `nocturnal_spo2_events`
6. **行为关联（核心价值）**：
   - `medication_logs` 当日用药（剂量、时间、分类）
   - `supplement_records` 当日补剂（剂量、服用时间）
   - `workout` 当日运动（强度、结束时间、HR zone 分布 — 来自 P1a 的 `workout_hr_zones`）
   - `diet_records` 酒精、晚餐时间、咖啡因
   - `rhinitis_episodes` 当日鼻炎严重度
   - `garmin_data.training_readiness_score` 和 `training_status`（来自 P1a）— 训练过载可能间接影响睡眠
7. **规则引擎 → 可操作假设**（见下方"行为关联规则库"）

### 行为关联规则库

规则结构：`{trigger, evidence_needed, hypothesis, suggested_action, confidence, severity}`。所有规则落入 `backend/app/services/sleep/correlation_rules.py`，每条规则独立测试。

#### A. 药物相关（重点覆盖异丙托溴铵类呼吸道用药）

| 规则 | 证据 | 假设 | 建议 |
|---|---|---|---|
| 异丙托溴铵使用日 vs 未使用日 → ODI 下降 ≥30% | 同一周内至少 3 用 3 未用 | "异丙托溴铵对你的夜间氧饱和度有保护作用" | 维持现有方案，漏用建议补上 |
| 异丙托溴铵末次剂量 > 睡前 8h | 用药时间戳 + 睡眠开始 | "夜间阻塞期药效已过" | 调整末次使用到睡前 1-2h（遵医嘱） |
| 当日漏服 + ODI 升高 ≥2 | 用药缺口 + 事件 | "漏服与氧降相关" | 设置夜间用药提醒 |
| 同日服用第一代抗组胺 + REM 期氧降集中 | Med 分类 + 事件时间 | "镇静抗组胺可能加重阻塞" | 改为第二代非镇静抗组胺 |
| 苯二氮䓬类 / 阿片类 当日使用 + 氧降加重 | Med 分类 + ODI | "呼吸抑制风险" | 高优先级，提示医疗咨询 |

#### B. 补剂相关

| 规则 | 证据 | 假设 | 建议 |
|---|---|---|---|
| 褪黑素 入睡时段吻合 + 深睡时长增加 | 服用时间 + 睡眠分期 | "褪黑素改善入睡与深睡" | 维持 |
| 镁剂（睡前）+ 事件数下降 | 服用时间 + 事件 | "夜间镁剂或有益" | 可保留 |
| 鱼油 + 抗凝药并用 | 已有 SafetyGuardian DSI 规则 | 已有规则 | — |
| 咖啡因下午后摄入 + 入睡困难 + 事件前移 | 摄入时间 + 入睡时长 | "咖啡因影响入睡稳定性" | 14:00 后断咖啡因 |
| 补剂无关联性（服用 vs 未服用夜间指标无差异） | 4 周对比样本 | "该补剂对睡眠无明显作用" | 纳入"简化补剂方案"建议 |

#### C. 运动相关（用 P1a 的 HR zones + training_readiness）

| 规则 | 证据 | 假设 | 建议 |
|---|---|---|---|
| 高强度训练（Z4+ >20min）结束 < 3h 入睡 | Garmin activity + 睡眠开始 | "运动过晚 → 交感未平复 → 入睡差、夜间 HR 高" | 改到睡前 4h 以上 |
| 力量训练 日 + 深睡增加 | 活动类型 + 睡眠分期 | "力量训练对深睡有益" | 维持 |
| 一周累计中高强度 < 150 min + ODI 偏高 | Intensity minutes + ODI | "运动不足可能加重阻塞" | 每周 ≥150 min 中等强度 |
| Garmin `training_status=overreaching` + HRV 下降 + ODI 升高 | training_status + HRV + 事件 | "训练过载诱发睡眠质量下降" | 下一周 deload |
| 连续零运动 ≥ 7 天 + 睡眠分期恶化 | 活动历史 + 睡眠 | "久坐降低睡眠质量" | 恢复基础有氧 |

#### D. 饮食 / 环境

| 规则 | 证据 | 假设 | 建议 |
|---|---|---|---|
| 当日酒精 ≥ 1 standard drink + 事件集中前半夜 | diet + 事件 | "酒精诱发上气道松弛" | 晚上不饮酒或量减半 |
| 晚餐结束 < 2h 入睡 + 事件在入睡初期 | diet 时间 + 事件 | "胃食管反流可能" | 晚餐与睡眠至少间隔 2.5h |
| 鼻炎严重度 ≥ 中 + ODI 升高 | rhinitis + ODI | "鼻阻塞继发 OSA 样事件" | 睡前鼻腔冲洗 + 鼻喷 + 侧卧 |
| PM2.5 > 75 当日 | env + 事件 | "空气质量触发气道反应" | 空气净化器 + 关窗 |

### 关联输出结构

```json
{
  "night_date": "2026-04-23",
  "odi": 7.2,
  "min_spo2": 87,
  "events_count": 12,
  "behavior_correlations": [
    {
      "category": "medication",
      "subject": "异丙托溴铵",
      "rule": "late_dose",
      "evidence": { "last_dose_ts": "...", "sleep_start_ts": "...", "gap_hours": 9.2 },
      "hypothesis": "末次用药距入睡 9.2h，药效高峰已过",
      "suggested_action": "将末次用药时间提前到 21:30-22:00",
      "confidence": "medium",
      "severity": "info"
    }
  ],
  "action_priorities": [
    "调整异丙托溴铵用药时间",
    "高强度训练避开睡前 3h",
    "鼻腔冲洗 + 侧卧"
  ]
}
```

### 4 周滚动对比分析

- `analyze_period(user_id, start, end)`：A/B 对比（用药 vs 未用 / 运动 vs 休息 / 饮酒 vs 未饮）
- 输出"某行为改变后 ODI 均值变化 ± 统计显著性"
- API: `GET /sleep/spo2/insights?weeks=4` 返回这个对比结果
- 前端渲染"行为→睡眠影响"条形图

### API（P1b 新增）

- `GET /sleep/spo2/analysis?night_date=YYYY-MM-DD` — 单夜分析 + 关联
- `GET /sleep/spo2/insights?weeks=4` — 多周行为对比
- `POST /sleep/spo2/reanalyze` — 重跑分析

### Twin 集成

- `twin/schema.py::Physiological` 新增 `nocturnal_spo2_min` / `nocturnal_odi` / `nocturnal_events_count`
- `twin/builder.py` 从 `nocturnal_spo2_events` 填

### Mobile 可视化

扩展 `mobile/components/sleep/SpO2NightChart.tsx`：
- 主轴：SpO2 曲线
- 次轴：HR + 呼吸率叠加（可切换）
- 标记点：氧降事件（红色三角）
- 背景色带：睡眠分期
- 下方卡片：ODI / 最低 SpO2 / 事件数 / **"今晚可试"行动建议**（来自 `action_priorities`）

### 测试

- `tests/test_nocturnal_spo2_analyzer.py`（平稳夜 / OSA 模式 / 酒精诱发 / 鼻炎继发）
- `tests/test_correlation_rules.py`（每条规则独立用例）
- `tests/test_sleep_spo2_api.py`

### 验收标准

- 对用户 3 某一夜调分析 API → 返回 events + ODI + 至少 1 条 hypothesis
- 4 周对比 API 能识别出"运动日 vs 休息日 ODI 差异"
- Mobile 曲线能看到事件标记 + "今晚可试"建议卡片
- **产品级验收**：你能在 App 上看到自己的波动模式并采取一个建议行动

### 预估工作量

| 模块 | 行数 |
|---|---|
| Migration + 事件模型 | ~80 |
| 分析服务（事件检测 + 关联引擎） | ~400 |
| 规则库（药/补剂/运动/饮食/环境） | ~350 |
| API 3 个 | ~200 |
| Twin 集成 | ~50 |
| Mobile SpO2NightChart 扩展 + 行动卡片 | ~500 |
| 测试 | ~500 |
| **合计** | **~2080** |

约 1.5-2 周。

### Rollback

- 新表独立可删
- 分析服务无副作用
- Feature flag `NOCTURNAL_ANALYSIS_ENABLED`

---

## Phase 2+ 次优先：其他 specialist 集成（在 P1a 数据上）

P1a 做完后，下面这些 specialist 升级基本只是"读 P1a 已存的数据"，不需要再 collector 工作：

| Phase | 内容 | 依赖 P1a 哪部分 |
|---|---|---|
| P2 | RecoveryCoach 用真 HRV 逐夜序列替换日均 | `nightly_readings` (metric=hrv) |
| P3 | MovementCoach 用 Garmin `training_status` 做交叉验证 | `garmin_data.training_status` |
| P4 | LongitudinalAnalyst 加 RHR 90 天 trend + intensity 周汇总 | `garmin_data.resting_heart_rate` + `intensity_minutes` |
| P5 | FuelStrategist 若有 Index 秤数据 → 用真体脂做 TDEE | `body_composition_measurements` |
| P6 | SafetyGuardian 新增 "设备 48h 未同步" 规则 | `garmin_devices` |
| P7 | MentalHealthCompanion 压力峰值检测 | `nightly_readings` (metric=stress) |

每个 P2+ 阶段预估 ~300-500 行（主要是 specialist 分支 + 测试），因为数据已经在库里了。

---

## 跨 Phase 风险与对策

| 风险 | 对策 |
|---|---|
| `garminconnect` 某个方法对部分账户 404（设备不支持） | collector 层 `try/except` 只 warn，不抛；测试覆盖 404 场景 |
| 夜间时序单表行数大（~500 行/夜/指标 × 5 指标 × 365 天 ≈ 90 万行/用户/年） | 索引 `(user_id, night_date)` 必有；6 个月后迁到分区表；归档老数据 |
| `hrv_7day_avg` 和新逐夜 baseline 口径不一致 | P1 保持双写，让 QA 能对账 |
| Specialist 集成点改动破坏现有 contract | 每个 Phase 的 specialist 改动都加 feature flag 控制分支 |
| 部署回滚复杂 | 每个 Phase 独立 PR；migration 都配 rollback.sql；feature flag 作为 safety net |

## 开工前待确认

- [ ] 新的 P1a（全面采集）+ P1b（分析）+ P2+（应用）三层架构是否 OK
- [ ] P1a 是否先做用户 3 的 30 天回填，验证数据质量后再全量上线
- [ ] P1b 的 specialist `NocturnalSpO2Analyst` 做不做（先只做分析服务 + API + Mobile 可视化，后续看需要加 specialist？）
- [ ] Feature flag 命名统一：`NOCTURNAL_ANALYSIS_ENABLED` + `GARMIN_COLLECT_*` 系列？
- [ ] 是否允许我在 P1a 开始前先做一个小改动：把 auth.py / scheduler.py / data_collection.py 的 `logger.error(f"... {e}")` 改为 `logger.error(..., exc_info=True)`（解决昨天"解密失败:"空异常那种无信息 log，此事独立、10 行代码）

