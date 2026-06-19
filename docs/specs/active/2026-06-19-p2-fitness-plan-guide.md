# P2 后端:C1 周健身计划 + C2 动作图文指导

- 状态:已实现(backend)。配套 mobile 并行开发,对齐下方 API 契约。
- 范围:`backend/` only。不触 `apps/rokid-*` / `apps/watch`。
- 自治层级:C1 = **T2**(系统起草 → 用户一键确认才落地);C2 = 只读确定性数据集。

## 数据流

```
GET /fitness/weekly-plan
        │  本周已有计划? ──是──▶ 返回(proposed/confirmed)
        │       否
        ▼
  build_twin(use_cache=True)
        ▼
  movement_coach 矩阵(复用 coach._resolve_training_status / _today_intensity / _gene_bias)
   + ACWR + readiness(recovery_coach) + ACTN3 基因偏好 + acute 病情门控
        ▼
  day_type 序列(hard/easy/rest,确定性,高 ACWR/低恢复→更多 rest)
        ▼
  7 天结构化 days[] ──▶ FitnessPlan(status=proposed)

POST /fitness/weekly-plan/confirm  (T2)
        ▼
  原子 UPDATE...WHERE status='proposed' 的 rowcount 门(确认幂等)
        ▼
  非 rest 日 → SmartReminder(source='fitness_plan',extra_data.fitness_plan_id+date)
        ▼
  落到提醒通道 / day timeline(与药同源的 SmartReminder 出口)
```

## 安全设计(safety review 关注点)

- 全程 hedge:无处方剂量、无医疗/治疗裁决(守 R4)。
- `disclaimer` 含「伤病/不适先就医 + 非医疗建议」。
- rationale 引用健康指标处标「(相关非因果)」。
- C2 是**人工策展确定性数据集**(`services/exercise_guide.py`),**绝不** LLM 生成(幻觉出的错误姿势/伤病建议是安全风险)。每条动作必带非空 `injury_red_lines` + `safety_note`(导向就医)。
- C1 当前 rationale 全确定性文本,不进 LLM 路径 → 无 PII 外泄面。
- IDOR:user_id 一律取自 token;confirm/dismiss 按 (id,user_id) 过滤,别人的 plan → 404。

## 幂等三层

1. 一周一行(`UniqueConstraint user_id+week_start`):同周重复 GET 返回既有 plan,不重复提议;并发插入撞约束 → 收敛既有行。
2. confirm 原子 `UPDATE...WHERE status='proposed'` 的 rowcount 门:并发双确认只有一路 claim,另一路收敛到既有排程数。
3. 每条排程前按 (plan_id, date) 去重(Python 过滤 `SmartReminder.extra_data`,跨 PG/SQLite 可移植——不用 JSON-path SQL 数值强转,曾踩 count 误返 0)。

确认两次 → `scheduled_count` 稳定,SmartReminder 行数不翻倍(测试守门)。

## API 契约(已 pin,mobile 对齐)

- `GET  /api/v1/fitness/weekly-plan` → WeeklyPlanOut(7 天,`workout.duration_min` 整数)
- `POST /api/v1/fitness/weekly-plan/confirm` `{plan_id}` → `{confirmed,plan_id,scheduled_count}`
- `POST /api/v1/fitness/weekly-plan/dismiss` `{plan_id}` → `{dismissed}`
- `GET  /api/v1/fitness/exercise-guide` → `{exercises:[{exercise_key,name}]}`
- `GET  /api/v1/fitness/exercise-guide/{key}` → 完整条目;未知 key → 404

字段精确 shape 见 `backend/app/api/fitness.py` 的 Pydantic response model。

## 文件

- 模型:`backend/app/models/fitness_plan.py`(注册于 `models/__init__.py`)
- 迁移:`backend/migrations/managed/20260619_120000_create_fitness_plans.{postgresql,sqlite}.sql`
- C1 service:`backend/app/services/fitness_plan_service.py`
- C2 dataset:`backend/app/services/exercise_guide.py`
- 路由:`backend/app/api/fitness.py`(挂 `app/api/main.py`)
- 测试:`backend/tests/test_fitness.py`

## C2 exercise_key 命名空间

`pushup / squat / plank / pullup / lunge / glute-bridge`。C1 周计划的 `workout.exercise_key`(非空时)必须命中本集合(测试守门),与 C3 Rokid(pushup)共用命名空间——改名要全链路同步。
