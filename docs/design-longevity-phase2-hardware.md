# 设计文档:无感硬件接入(抗衰 Phase2 W5)

> 状态:接入设计 · 2026-06
> 上游:`docs/plan-longevity-phase2.md` §W5、`docs/strategy-longevity-os.md` §7(数据层)
> **诚实定位**:W5 是 Phase 2 里**唯一非纯代码**的工作流。戒指/床垫厂商未定、无 SDK,
> 此时写"骨架适配器"等于 noop 假装(违反工程铁律 #1)。故本文只给**接入设计 + 工程预留点**,
> 真正落地代码要等硬件商务(选型 + 贴牌 + SDK 授权)确定后再写。

---

## 0. 为什么是设计文档而不是代码

- 戒指/床垫是**贴牌/集成**(战略 §5:不自建硬件)。厂商(小米/Oura 类戒指、Withings/Eight 类床垫)未定 → 无 API/SDK 契约 → 无法写真实 adapter。
- 写一个 `raise NotImplementedError` 或静默返回空的 adapter = 假装有能力,违反"不假装成功"。
- 因此 W5 **不开 PR、不进代码库**;本文记录"厂商一旦确定,工程怎么 1-2 天接进来"。

---

## 1. 好消息:适配层已就绪

仓库已有成熟的设备适配框架(`backend/app/services/device_adapters/`):
- `base.py`:`DeviceAdapter` ABC + `DeviceType` / `AuthType` 枚举 + `NormalizedHealthData` 标准化结构
- `manager.py`:`DeviceManager.register_adapter(device_type, adapter_class)` 注册表
- 已实现:`apple` / `healthkit` / `huawei` / `withings`

**意味着接新硬件 = 实现一个 `DeviceAdapter` 子类 + 注册,不动框架。** 这是 Phase 2 选"贴牌+集成"而非自建的工程红利。

---

## 2. 接入契约(厂商确定后照此实现)

新建 `device_adapters/<vendor>_ring.py`(或 `_mattress.py`),实现 ABC:

```
class <Vendor>RingAdapter(DeviceAdapter):
    device_type -> DeviceType.<NEW>          # base.py 的 DeviceType 加一枚举
    auth_type   -> AuthType.OAUTH / API_KEY  # 看厂商
    async authenticate(credentials) -> bool
    async test_connection() -> dict
    async fetch_daily_data(target_date) -> NormalizedHealthData | None
```
然后 `DeviceManager.register_adapter("<vendor>_ring", <Vendor>RingAdapter)`。

> 真实失败必须让调用方感知(抛/返 None),**禁止** noop fallback —— 与现有 adapter 一致。

---

## 3. 信号 → Twin 映射(抗衰要的就这几路)

抗衰只需要无感戒指/床垫能稳定产出的几路信号,且 Twin 字段**已存在**:

| 硬件信号 | NormalizedHealthData | Twin 字段(已存在) | 抗衰用途 |
|---|---|---|---|
| HRV | hrv | `physiological.hrv_latest` / `hrv_nightly_series` | 恢复/压力 → RecoveryCoach |
| 静息心率 | resting_hr | `physiological.resting_hr` | 心血管基线 |
| 睡眠时长/分期 | sleep_* | `physiological.sleep_duration_h_latest` / `sleep_score_latest` | 四件套"睡眠"支柱 |
| 夜间 SpO2 | spo2 | `physiological.spo2_avg` / `spo2_min_overnight` | OSA 筛查 |
| 夜间呼吸率 | respiration | `physiological.respiration_nightly_avg/stddev` | OSA 信号 |
| (床垫)体动/在床时间 | — | 需 BehavioralState 加字段 | 睡眠连续性 |

**关键**:除床垫体动外,戒指信号全部落到**已有 Twin 字段** → 接进来即被 RecoveryCoach / SafetyGuardian / LongevityWatch(W1)消费,无需改下游。VO2max(W2)、PhenoAge(MVP)不依赖硬件。

---

## 4. 数据流(厂商确定后)

```
戒指/床垫 App/Cloud
   ↓ OAuth / API（厂商 SDK)
<Vendor>RingAdapter.fetch_daily_data → NormalizedHealthData
   ↓ DeviceManager 统一入库 daily_health (同 garmin/withings 路径)
twin/builder._fill_* → physiological.{hrv,sleep,spo2,respiration}
   ↓
RecoveryCoach / SafetyGuardian / longevity_watch(W1)主动监测
```

---

## 5. 工程预留(现在就能做的,0 商务依赖)

这些不依赖厂商,可在 W5 真正接入前先行(若要开 PR):
1. `DeviceType` 枚举预留 `SMART_RING` / `SLEEP_MAT`(纯枚举,无行为)——**但** 没有 adapter 时加枚举意义不大,建议厂商定了再加,避免悬空。
2. 床垫体动字段:`BehavioralState` 可预留 `bed_time_minutes` 等(Optional,向后兼容)——同样建议有真实数据源再加。

> 结论:**现在不预留空壳**(避免死代码/假装),等厂商确定一次性接入。本文即"接入说明书"。

---

## 6. 商务依赖与排期(非工程)

| 步骤 | 负责 | 说明 |
|---|---|---|
| 戒指/床垫选型 | 创始人/BD | 无订阅、贴牌可行、SDK 开放 |
| 贴牌/数据授权商务 | BD | 拿到 API/SDK + 数据合规授权 |
| adapter 实现 + 注册 | 工程(1-2 天) | 照 §2/§3,有 SDK 后很快 |
| 依从率小样本验证 | 产品 | 先验"用户愿不愿戴/铺",再谈规模 |

**排期纪律**:W5 不能按纯工程排期;adapter 那 1-2 天只是末段,前面全是商务。

---

## 7. 风险与边界
- 医疗器械/数据合规:贴牌设备的数据出境/存储按隐私 Tier 处理(同 Garmin/Withings)。
- 不夸大:戒指 HRV/睡眠是消费级估算,标来源与可信度,不当临床诊断。
- 依从率是硬约束:无感 ≠ 零摩擦,小样本先验。

---

## 附:诚实声明
本文是接入设计,非可执行代码。device_adapters 框架(DeviceAdapter ABC / DeviceManager / NormalizedHealthData)与 Twin physiological 字段均已核实存在。W5 真实落地依赖硬件商务(厂商/SDK/授权),工程实现仅为末段 1-2 天;在此之前不写空壳 adapter(避免假装成功)。
