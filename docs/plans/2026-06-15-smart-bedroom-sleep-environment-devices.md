# 智能卧室睡眠环境设备设计文档

> 日期: 2026-06-15  
> 状态: v1 设计稿  
> 目标: 用当前 Reva / Personal Health OS 串联米家、小米生态、Aqara、Home Assistant、青萍、松下壁挂式新风、窗帘、灯光、空调、湿度控制、空气净化和床垫/睡眠监测, 形成可观测、可控制、可复盘的睡眠环境闭环。

## 1. 核心结论

推荐采用 **米家/Aqara + Home Assistant + Reva Health OS** 的混合架构:

```text
设备生态: 米家 / Aqara / Yeelight / 青萍 / 松下新风 / 空调伴侣 / 净化器 / 湿度设备
控制桥: Home Assistant 本地统一状态、场景、自动化和跨生态桥接
健康层: Reva Health OS 做策略、Agenda、Review、Outcome Proof、审计
```

裁决:

- **米家/Aqara 负责可用性**: 家人能用米家、小爱、Aqara App 和实体开关兜底。
- **Home Assistant 负责统一控制面**: CO2、PM2.5、温湿度、睡眠状态、室外 AQI 和设备状态需要在同一规则引擎里判断。
- **Reva 不做实时家居控制器**: Reva 只下发健康意图和场景触发, 不直接任意控制单个设备。
- **先做 CO2 + 新风闭环**: 这是卧室睡眠环境 ROI 最高的环节, 先验证 7 晚数据再买昂贵床垫。
- **不要第一阶段买高价“AI 智能床垫”**: 温控、监测、床垫舒适度拆开买, 通常更便宜、更可靠。

## 2. 产品目标

用户侧:

1. 睡前自动进入低刺激环境: 遮光、暖暗光、合适温湿度、干净空气。
2. 夜间自动维持环境: CO2 不积累, PM2.5 不升高, 湿度不过干/不过湿, 空调不忽冷忽热。
3. 起床更自然: 日出灯、窗帘渐开、新风提前换气、空调回到清醒温度。
4. 第二天能复盘: 环境曲线关联 RingConn、Apple Watch、Garmin、睡眠监测和主观精力。
5. 出问题不靠记忆: 传感器离线、滤芯到期、加湿器缺水、新风无响应进入 Agenda。

系统侧:

- 建立 `BedroomEnvironmentSnapshot`: CO2、PM2.5、温度、湿度、TVOC、照度、占用、床上状态、设备状态。
- 建立 `BedroomSleepProtocol`: 睡前、入睡、夜间、起床、午睡、生病/鼻炎、深度恢复。
- 通过 Home Assistant Adapter 把设备状态和场景事件进入 Reva。
- 通过 HealthAgenda 生成设备维护、数据质量、睡眠保护和复盘任务。
- 所有自动化有手动 override、审计、降级路径。

非目标:

- 不诊断疾病, 不把 CO2、睡眠分期或打鼾自动解释成疾病。
- 不追求全屋智能, 只做卧室睡眠环境。
- 不让 LLM 直接控制设备。
- 不把 Home Assistant 暴露公网。
- 不在第一阶段购买高价国产 AI 床垫、智能止鼾枕、远红外/石墨烯床品。

## 3. 三种路径

| 路径 | 优点 | 缺点 | 判断 |
|---|---|---|---|
| 米家-only | 最快、便宜、家人易用 | Reva 难稳定拿状态, 复杂规则和复盘弱 | 可做 Phase 1 兜底 |
| Home Assistant-only | 本地化、跨生态、可审计 | 初装维护成本高, 家人门槛高 | 适合折腾党 |
| 混合架构 | 落地快, 可复盘, 家人可用, 可逐步本地化 | 需要治理两套场景边界 | **推荐** |

## 4. 总体架构

| 层 | 组件 | 负责 | 不负责 |
|---|---|---|---|
| 传感层 | 青萍 CO2/PM2.5/温湿度/TVOC、Aqara 人体/门窗/照度、RingConn/Apple Watch/Garmin/睡眠带、室外 AQI | 采集环境和睡眠事实 | 判断健康目标 |
| 执行层 | 窗帘、灯光、空调、松下新风、净化器、加湿/除湿、水暖毯 | 改变物理环境 | 自行调参 |
| 控制层 | 米家/Aqara/Yeelight/Home Assistant | 配网、场景、实体状态、设备命令 | 医疗判断、长期复盘 |
| 健康层 | HomeAssistantAdapter、BedroomEnvironmentSnapshot、BedroomSleepProtocol、HealthAgendaItem、Sleep Review | 阈值策略、协议、Agenda、审计、Outcome Proof | 高频实时设备驱动 |

## 5. 设备接入策略

优先级:

1. 本地 Matter/Thread/Zigbee/HomeKit/Mi Home 可见设备。
2. Home Assistant 官方集成: Xiaomi Home、Qingping、Matter、Thread、HomeKit Controller。
3. 小米官方 Home Assistant integration 或 Xiaomi Home credentials。
4. Aqara Hub M3 / 小米中枢网关 / 米家网关桥接。
5. 红外控制: 空调、新风、老设备。
6. 社区自定义集成: 只用于非关键路径, 保留原厂 App。
7. 干接点/继电器: 仅设备说明书允许且由电工确认后使用。

关键现实:

- Thread 不等于 Matter, 买新设备必须看 Matter 标识。
- 小米 Home Assistant local mode 在中国大陆中枢网关下更有价值; 没有中枢时很多控制可能仍走云。
- 青萍设备可作为 HA 本地传感器来源, 但部署位置比品牌更重要。
- 松下新风必须先确认型号和控制方式, 不可假设一定有 HA 官方集成。

## 6. 设备设计

### 6.1 环境传感器

第一优先级是青萍 CO2/PM2.5/温湿度设备、门窗传感器, 可选加一个空调回风处或卧室门口温湿度传感器。青萍应放在离床头 1-2 米、接近呼吸高度的位置, 避开新风口、空调口、加湿器和窗户缝。

| 指标 | 目标 | 动作 |
|---|---|---|
| CO2 | 理想 <900ppm; 1000ppm 开始通风; 1200ppm 增强; 1500ppm 强干预 | 新风/开窗提醒 |
| PM2.5 | 越低越好 | 净化器/新风过滤 |
| 湿度 | 40%-60%; 鼻炎/干燥敏感 45%-55% | 加湿/除湿 |
| 温度 | 睡前略凉, 夜间稳定, 醒前回升 | 空调/控温垫 |
| 光照 | 睡前暖暗, 夜间全暗, 醒前渐亮 | 灯光/窗帘 |

### 6.2 窗帘和灯光

窗帘优先选择 Aqara/米家/SwitchBot 免改或半改造电机; 可施工时用隐藏式电动轨道 + 高遮光布, 遮光卷帘/蜂巢帘通常优于普通开合帘。灯光用 Yeelight/米家可调色温主灯、低亮暖色床头灯、人体传感器起夜灯。自动化为睡前 30-60 分钟窗帘关闭和灯光渐暗, 夜间离床只开 1%-5% 暖光, 起床前 15-30 分钟日出渐亮后窗帘渐开。

### 6.3 空调

智能空调走厂商/米家到 HA; 普通空调用米家空调伴侣 Pro、Aqara M3 红外或 BroadLink 红外。控制依据以床头外置温湿度为主, 不只信空调回风温度。规则是睡前预冷/预热, 入睡后静音、防直吹、减少跳变, 夜间只微调, 人工调温后 120 分钟内不覆盖, 除非空气质量或安全规则触发。

### 6.4 松下壁挂式新风

未确认具体型号前, 按三种路径设计:

| 路径 | 条件 | 说明 |
|---|---|---|
| 原厂 App / 松下智家 | 新风带 Wi-Fi 或云控 | 可试社区 HA 集成, 但保留原厂 App |
| 红外遥控 | 有红外遥控器 | 用 Aqara M3/小爱音箱 Pro/米家红外学习开关和档位 |
| 干接点/墙控 | 说明书支持外部控制 | 电工确认后接入, 不自行改强电 |

最低抽象:

```text
fan.bedroom_fresh_air = off | low | medium | high | boost
state_confidence = high | medium | low
```

如果只能红外单向控制, `state_confidence=low`, Reva 不假装知道真实档位。

CO2 规则:

- CO2 >1000ppm 持续 10 分钟: 新风 low/medium。
- CO2 >1200ppm 持续 10 分钟: 新风 high。
- CO2 >1500ppm 持续 5 分钟: boost 30 分钟 + 轻提醒。
- 室外 PM2.5 高或花粉/雾霾高: 优先新风过滤和净化器, 不建议开窗。
- 夜间噪声敏感: 优先 medium 长时间运行, 少用 high/boost。

### 6.5 净化器和湿度控制

净化器用米家空气净化器 4 Pro / Pro H 或同等级夜间低噪机型: 睡前 30 分钟预净化, 夜间默认静音, PM2.5 高时短时提升。湿度以床头青萍/Aqara 为准: <35% 持续 15 分钟加湿到 45%-50%; 40%-60% 维持; >65% 持续 30 分钟关加湿并视室外条件开除湿/新风/空调除湿; 缺水只生成 Agenda, 不夜间强提醒。

### 6.6 床垫、床品和监测

推荐路径: 舒服的普通床垫 + 双区水暖毯/控温垫或相变床品 + 现有 RingConn/Apple Watch/Garmin 作为结果源。需要非接触监测时再考虑 Withings Sleep/小米睡眠监测带; 有明确打鼾/疑似 OSA 时优先医学检查或更可靠监测, 不靠智能枕头自我安慰。

## 7. BedroomSleepProtocol

| 对象 | 关键字段 |
|---|---|
| `BedroomSleepProtocol` | `room_id`, `status`, `target.co2_ppm`, `target.humidity_percent`, `target.temperature_c`, `target.light`, `devices.sensors`, `devices.actuators`, `scenes[]`, `safety.manual_override_minutes`, `safety.max_night_notifications` |
| `BedroomEnvironmentSnapshot` | `room_id`, `captured_at`, `co2_ppm`, `pm25`, `temperature_c`, `humidity_percent`, `illuminance_lux`, `occupancy`, `bed_presence`, `sources`, `confidence`, `stale` |
| `BedroomAutomationEvent` | `event_type`, `reason`, `command.entity_id`, `command.mode`, `source`, `manual_override`, `audit_ref` |

默认阈值: CO2 `ideal=800`, `soft_limit=1000`, `high=1200`, `critical=1500`; 湿度 `low=35`, `target=45%-55%`, `high=65`; 夜间亮度 `1%-5%`; 手动 override `120` 分钟。

## 8. 自动化场景

| 场景 | 触发 | 动作 |
|---|---|---|
| 睡前准备 | 固定时间、日程、用户点“我要睡觉了”、进入 sleep window | 窗帘关闭, 灯光暖色渐暗, 空调预冷/预热, 新风提前换气到 CO2 <900ppm, 净化器预清洁, 湿度调到 45%-55%, Reva 记录 `sleep_protection_window_started` |
| 入睡后 | 床垫/睡眠带/RingConn/Watch 判断已入睡, 或睡前场景后 30-60 分钟无人操作 | 关主灯, 保留起夜灯, 空调进入静音曲线, 新风按 CO2 闭环调档, 净化器睡眠档, 禁止 P1/P2 提醒 |

### 夜间空气闭环

```text
if CO2 > 1000ppm for 10m: fresh_air = medium
if CO2 > 1200ppm for 10m: fresh_air = high
if CO2 > 1500ppm for 5m: fresh_air = boost 30m + notify once
if PM2.5 high: purifier = auto/medium; avoid window advice
if humidity < 35% for 15m: humidifier = on until 45%-50%
if humidity > 65% for 30m: humidifier = off; dehumidify/ventilate
```

防抖:

- 阈值必须有持续时间。
- 设备命令有最短间隔。
- 人工操作进入 120 分钟 override。

起夜和起床: 人体/离床只触发 1%-5% 暖光, 不开主灯, 5 分钟无人关闭; 起床时灯光 15-30 分钟渐亮, 窗帘渐开, 新风提升 15-30 分钟, 空调回白天温度, Reva 生成 morning bedroom summary。

## 9. Reva 改造点

后端新增 `HomeAssistantAdapter`、`BedroomEnvironmentService`、`BedroomSleepProtocolService`、`BedroomOutcomeAnalyzer`, 分别处理 HA REST/Webhook/entity/service allowlist、快照/规则/事件、HealthProtocol 到场景和 Agenda 的投影、环境指标和睡眠结果关联。

建议 API:

```http
GET  /api/environment/bedroom/current
GET  /api/environment/bedroom/history?days=7
POST /api/environment/bedroom/events
GET  /api/environment/bedroom/recommendation
POST /api/integrations/home-assistant/test
POST /api/integrations/home-assistant/webhook
POST /api/integrations/home-assistant/scenes/{scene_id}
```

三端: Mobile 显示昨夜卧室环境、Sleep Protocol 设置、Manual override、设备异常 Agenda; Mac App 提供卧室环境调试、HA entity 映射、7 夜对比和 Trace; Web 管理 HA URL/token/entity mapping/权限、设备清单、环境历史、导出和审计日志。

## 10. 数据流

状态上行: 青萍/米家/Aqara/空调/新风/净化器 -> Home Assistant entity states -> Reva 每 1-5 分钟拉取 -> `BedroomEnvironmentSnapshot` -> HealthAgenda/Review/Outcome Proof。

事件上行: HA automation -> `POST /api/integrations/home-assistant/webhook` -> `BedroomAutomationEvent` -> AuditLog -> Review。

命令下行: Reva protocol decision -> allowlisted scene command -> Home Assistant REST API -> HA scene/script -> device command -> state confirmation -> `BedroomAutomationEvent`。

Reva 只调用场景级命令:

- `scene.sleep_prep`
- `scene.sleep_asleep`
- `scene.wake_gentle`
- `script.ventilation_boost_30m`
- `script.humidity_restore`

## 11. 安全、隐私和降级

安全: HA token 加密存储; HA 地址只允许内网或 VPN; Reva 默认只读, 写命令需用户显式启用; 只允许 allowlist scene/script, 不允许任意 service 调用; 所有命令写 AuditLog; 居住状态和睡眠环境数据不发给通用 LLM。人工控制后对应设备进入 override window, 床头实体开关能立即关闭自动化, 夜间非紧急提醒最多 1 条。

降级:

| 故障 | 降级 |
|---|---|
| HA 离线 | 米家原生场景继续跑, Reva 记录缺失 |
| 青萍离线 | 不做 CO2 自动控制, 生成 data_quality item |
| 新风无响应 | 提醒一次, 不重复轰炸命令 |
| 空调红外单向 | 标记低置信, 不做复杂闭环 |
| 室外 AQI 缺失 | 不建议开窗, 优先净化器/新风过滤 |

## 12. 落地路线

| 阶段 | 任务 | 完成标准 |
|---|---|---|
| Phase 0: 7 晚基线 | 安装青萍和必要传感器; 记录 7 晚 CO2/温度/湿度/PM2.5; 同步 RingConn/Apple Watch/Garmin/睡眠监测结果 | 看到每晚 CO2 max、CO2 >1000ppm 时间占比、湿度、温度、PM2.5, 并和晨起精力/睡眠评分/HRV/RHR 初步对比 |
| Phase 1: 米家/Aqara 基础场景 | 窗帘睡前关起床开; 灯光日落/日出; 空调睡前预冷/预热; CO2 触发新风; 湿度低触发加湿; PM2.5 触发净化器 | 不依赖 Reva 也能维持基本环境, 家人能手动控制和关闭自动化 |
| Phase 2: Reva 接入 HA | Home Assistant Adapter; Entity mapping; Snapshot/Event; Mobile Today 卡片; Mac Trace | Reva 能读卧室状态、生成 data_quality Agenda、解释昨夜自动化, 且只通过 allowlist 触发场景 |
| Phase 3: 卧室健康协议 | `BedroomSleepProtocol`; 睡前/入睡/夜间/起床场景协议; 鼻炎/恢复/训练日 profile; 周复盘调参 | 用户能选择 profile, 系统能按过去 7 晚建议调参 |
| Phase 4: Outcome Proof | A/B 测试新风闭环或不同 CO2 目标; 关联深睡、醒来次数、HRV、RHR、SpO2、晨起精力; 4 周复盘 | 标记为个人实验, 说明哪些环境调整可能有用, 哪些没明显作用 |

## 13. 验收指标

环境: CO2 夜间 P95 <1000ppm, CO2 >1200ppm 时间占比下降, 湿度 40%-60% 时间占比提升, PM2.5 夜间保持低位, 温度夜间波动减少。

睡眠: 主观晨起精力 7 日均值提升, 夜间醒来次数下降, HRV/RHR 相对个人基线改善或稳定, 鼻炎/咽干/晨起头痛主观评分下降。

产品: 用户无需每天手动开新风/调灯/调空调, 夜间非紧急提醒不超过 1 条, 自动化误触发可手动 override, 设备离线进入 Agenda, 每条设备命令可追溯原因。

## 14. 初始采购建议

必买: 青萍 CO2/PM2.5/温湿度设备、空调伴侣或红外中枢、松下新风控制接入路径、Yeelight/米家/Aqara 可调色温灯、电动窗帘或窗帘机器人、空气净化器、加湿/除湿设备。

可选: 双区水暖毯/控温垫、相变床品、Withings Sleep 或小米睡眠监测带、电动床架。

不建议第一阶段买: 高价国产 AI 智能床垫、无可靠证据的国产智能止鼾枕、远红外/石墨烯/量子/负离子类高溢价床品、需要复杂海外订阅且无大陆售后的 Eight Sleep 海淘方案。

## 15. 待确认问题

1. 松下壁挂式新风具体型号、是否有红外遥控、是否接入松下智家 App。
2. 卧室面积、层高、窗户数量、是否双人睡。
3. 空调型号和是否已有米家/红外控制。
4. 是否已安装电动窗帘或预留窗帘盒。
5. 是否已有加湿器、除湿机、空气净化器。
6. 是否存在打鼾、疑似呼吸暂停、鼻炎、晨起头痛或夜间口干。
7. 是否愿意维护 Home Assistant 主机。

## 16. 参考依据

- Home Assistant REST API 可通过 `/api/services/<domain>/<service>` 调用服务, 适合作为 Reva 触发 HA 场景的下行路径: <https://developers.home-assistant.io/docs/api/rest/>
- Home Assistant Xiaomi Home 集成覆盖 Xiaomi Gateway、空气净化器、加湿器、空气质量监测、红外等设备, 且要求设备先接入 Mi Home: <https://www.home-assistant.io/integrations/xiaomi_miio/>
- 小米官方 Home Assistant integration 说明 local mode 依赖中国大陆 Xiaomi Central Hub Gateway 或带中枢能力的设备: <https://github.com/xiaomi/ha_xiaomi_home>
- Home Assistant Matter 文档提醒 Thread 设备不一定支持 Matter, 购买时必须确认 Matter 标识: <https://www.home-assistant.io/integrations/matter/>
- Home Assistant Thread 文档说明 Thread 边界路由器、凭据和网络偏好仍需要配置和排障: <https://www.home-assistant.io/integrations/thread/>
- Home Assistant Qingping 集成支持 Air Monitor Lite、CO2 Temp RH 等设备: <https://www.home-assistant.io/integrations/qingping/>
- Xiaomi Smart Home Hub 2 官方说明支持 Bluetooth、Bluetooth Mesh、ZigBee: <https://www.mi.com/global/product/xiaomi-smart-home-hub-2/>
- Qingping Air Monitor Lite 官方页面说明支持米家中国大陆服务器和 Siri/HomeKit 相关能力: <https://www.qingping.co/air-monitor-lite/overview>
- Health Canada 对住宅 CO2 给出 1000ppm 的 24 小时长期暴露限值: <https://www.canada.ca/en/health-canada/services/publications/healthy-living/carbon-dioxide-home.html>
- ASHRAE Journal 关于卧室通风与睡眠的文章提到 CO2 超过 900ppm 时自动开启送风风扇的实验设计: <https://www.ashrae.org/news/ashraejournal/using-indoor-air-quality-tactics-to-sleep-better-at-night-perform-well-the-next-day>
