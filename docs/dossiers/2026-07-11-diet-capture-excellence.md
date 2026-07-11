# Dossier: 饮食打卡极致体验

| 字段 | 值 |
|---|---|
| slug | `diet-capture-excellence` |
| 创建日期 | 2026-07-11 |
| 当前阶段 | S7 上线验证 |
| 状态 | device_validation_pending |
| 负责 | Codex |
| 反馈环 | Backend pytest / Mobile Jest + TypeScript / Simulator / backend deploy / EAS TestFlight + production OTA |

## Correct Course

- [ ] Correction Block

## S0 · 用户需求（逐字）

> 聚焦睡眠、运动和饮食三个主要功能。先把饮食打卡做到极致，准确性、性能和交互体验做到最好，并且可以分享小红书和微信，截屏，要有高级感，让95和00后人群感觉用这个App很有面子。

- 谁用 / 解决什么 / 现在怎么绕过：高频拍照、语音或文字记餐的 Mobile 用户；当前需要等待黑盒识别、手动核对一段合并文字，再以普通文本分享。
- 锚点用户相关性：饮食是每天发生多次的 Capture 闭环，也是睡眠、运动和代谢分析的数据基础。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `mobile/app/diet.tsx` 已有拍照 -> 识别 -> 草稿 -> 人工确认 -> 写入状态流。
  - `backend/app/services/ai/food_recognition.py` 已输出结构化食物、份量、宏量营养和视觉置信度。
  - `backend/app/services/food_nutrition_lookup.py` 与 reviewed food table 已用于语音和聊天草稿，但未接视觉识别。
  - `backend/app/api/diet.py` 已有 owner-scoped 私有图片、写入幂等键和 fail-closed 内容防护。
  - `mobile/utils/share.ts` 已有系统分享和微信可接受的 Web 分享回退。
- 已证实缺口：
  - 视觉结果直接信任模型营养值，明确克数没有用 reviewed food table 校准。
  - 视觉 `meal_description` 可与清洗后的 foods 不一致；fiber 没有完整贯通响应。
  - 确认卡只显示合并描述，未展开每个食物、份量、来源和低置信度。
  - 照片 base64 在识别与确认写入间重复上传，且草稿未具备服务端可恢复身份。
  - 近 30 天生产聚合中饮食记录有数据，但 `ai_recognized` / `image_url` 均无有效样本，食物识别 caller 也无可用时延样本；主入口可观测闭环缺失。
  - 现有分享是文本/链接，没有适配小红书 3:4 与微信分享的图片卡。
- 硬约束：营养是估算，不宣称医学精确；确认前不写 DietRecord；图片 owner 隔离；不引微信私有 SDK；失败必须可见且可重试。

## G1 · 准入裁决（governance §8 RequirementAdmission）

- first_class_objects：`ExecutionEvent`、`WriteIntent`、`HealthTwin`。
- core_loop_step：Capture -> 确认写入 -> Today/Review -> 分享反馈。
- target_surface / safety_level / autonomy_tier：Mobile + Diet API / privacy_sensitive / manual_confirm。
- spec_required：是；改变用户可见识别契约、健康写入数据来源和图片分享行为。
- smallest_end_to_end_slice：一张餐食照片得到可解释草稿，明确克数由营养表校准，用户确认后只写一次。
- stale_surface_to_remove：黑盒合并描述、无来源的伪精确营养、仅文本分享。
- **裁决：PASS**。用户已明确要求按优先级持续直接实施。

## S2 · PRD

- 链接：`docs/prd/2026-07-11-diet-capture-excellence.md`
- 引用权威：R5 Food Voice Capture、R10 Mobile 主体验、R4 确定性写入边界。
- 边界：不做诊断、处方、自动写入、食物秤级精度承诺或微信私有 SDK。
- 未决问题：无阻塞问题；外部食物数据库和分享模版 A/B 属后续增量。

## S3 · 规划

- 设计：`docs/plans/2026-07-11-diet-capture-excellence-design.md`
- 实施：`docs/plans/2026-07-11-diet-capture-excellence.md`
- Feature Spec：`docs/specs/active/2026-07-11-diet-capture-excellence.md`
- 顺序：P0 准确性/可纠错 -> P0.5 单次上传/幂等 -> P1 图片分享 -> 真机/生产指标。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge + 现有 DietRecord / private upload / system share contract 对照。
- 已焊入限制：只有明确重量单位才允许表值覆盖；无确定份量保留估算并降置信；分享必须用户显式触发；未确认草稿不可分享为“已记录”。
- 待拍板分叉：无。
- **裁决：PASS**。定义环文档无待澄清项，进入 P0。

## S4 · 研发任务分解

- [x] T1 视觉结果清洗、份量解析、营养表校准与 provenance（backend deploy）
- [x] T2 Mobile 分项确认卡、低置信提示和修正入口（OTA）
- [x] T3 服务端照片草稿身份、单次大载荷和写入幂等（backend deploy + OTA）
- [x] T4 3:4 高质感饮食分享卡、图片生成和系统分享（EAS）
- [x] T5 识别/确认/纠错/分享埋点与 p50/p95 看板（backend deploy + OTA）
- [x] T5.1 端侧照片压缩、相机返回后计时、成功样本分位数与无正文纠错率（backend deploy + OTA）
- [x] T5.2 模型输出边界、份量真实性、识别日志脱敏与可操作错误语义（待 backend deploy + OTA）
- [ ] T6 模拟器视觉、真机微信/小红书、生产数据闭环验收
- 并发检查：2026-07-11 `origin/main` 与当前干净集成 worktree 一致；原始用户工作区不纳入暂存。

## S5 · 实现

- T1：明确克重且命中审核食物表时覆盖模型营养值；只有数据层 `calibration_names` 显式批准的身份可覆盖，部分表字段采用 `mixed` 来源，“鸡肉/鸡蛋/豆腐”等泛化名称保留视觉估算并提示核对。商业多模态模型收到食物语境或 Mobile 默认纯图片提示时也必须先经过同一清洗与校准链路；普通视觉降级描述明确禁止作为饮食写入参数。
- T2：确认卡展示逐项食物、份量、热量、置信度、营养表/视觉估算来源，低置信或未校准份量提示核对。
- T3：识别成功返回 owner-scoped `photo_draft_token`，确认不再重复上传 Base64；确认、取消和过期清理用行锁串行化，成功确认后由 DietRecord 接管图片并删除草稿行，取消/过期擦除识别正文且在图片删除成功后删行，删除失败保留最小重试句柄并显式报错。正式记录删除采用可恢复 tombstone，每日任务按数据库引用恢复或物理删除。Mobile 以用户隔离的 SecureStore 保存 24 小时紧凑快照，不保存 Base64 或无界模型正文，进程重启后可恢复并继续确认或取消；缓存写入失败不阻断服务端确认，App 启动即执行过期物理清理。
- T4：新增固定 3:4 饮食故事卡；iOS 以 point/PixelRatio、Android 以 bitmap pixel 分别请求，模拟器实测输出 1080x1440 PNG。等待受保护图片加载，5 秒无终态自动使用指标版卡片；图片或原生捕获不可用时降级为不含私有 URL/标识的文本系统分享，系统分享结束后释放临时 PNG。分享图不含用户名或其他健康数据。
- T5：新增无正文的识别/确认/分享终态事件，观测聚合直接输出各阶段样本数、失败数、p50、p95；识别响应另带 vision/calibration/photo_draft/total 分段耗时。
- 上线前复核发现生产 `food_items` 为空，原校准迁移只能更新既有行，导致营养表校准在生产无法命中。标准部署现于受控迁移后幂等执行 `seed_food_nutrition.py`，并以测试锁定 6 项审核食物、6 项营养值和严格 `calibration_names`，不允许泛化“鸡肉”进入鸡胸肉校准范围。
- T5.1：相机不再直接生成 12MP 原图 Base64；饮食与聊天共用 OTA-safe 图片承重工具，最长边限制 1568px、JPEG q0.7 且不放大小图，并在识别/草稿持久化后清理临时编码文件。相机返回后显示“正在优化照片”，完成后才开始上传识别；埋点新增无正文的端侧准备耗时、压缩后字节数和确认纠错标记。观察看板只以 completed 样本计算 p50/p95，同时单列 attempts、failures、cancelled 和 correction rate，避免把取景和取消时间当成模型时延。
- T5.2：视觉 JSON 现在经过字段白名单、有限数值、最多 12 项、重复项和 intake intent 清洗；药物、补剂、卡片文字不会进入饮食草稿，负值/非数字/越界置信度转为未知。照片份量新增 `portion_basis` / `portion_confidence`，营养表校准后仍保持视觉估算；Mobile 显示“表值 × 估算份量”和定性识别信号，不再把模型自报置信度展示为精确百分比。正常与异常识别日志只记录长度、计数和错误类型，供应商正文、食物名和异常正文不写日志或回传。

## G3 · 测试闸

- 最新 focused backend regression：179 passed、1 PostgreSQL-only test skipped；同一并发测试在本机真实 PostgreSQL 运行 1 passed，覆盖 confirm/confirm、confirm/cancel、confirm/purge、cancel/purge。
- 合并最新主干后 full Mobile regression：233 suites、1625 passed；最终整改 focused regression：40 passed；TypeScript check passed。
- managed migration：SQLite 12 passed；PostgreSQL 实跑确认 `豆腐` 默认不校准、`北豆腐` 可校准、未知行默认关闭。
- Dossier consistency、OpenAPI type generation、system-map generation、doc-drift checks passed。
- iPhone 17 Pro 模拟器原生构建成功；430x932 页面和分享预览无重叠，系统分享面板成功接收 PNG；像素检查为 1080x1440、非空图像。
- LLM live-change regression gate：invariants 12/12、health_agent_core 50/50、真实 orchestrator 5/5，平均分 0.94；原始证据保存在本机 `/tmp/harness-live-final-20260711.log`。闸门同时修正两项既有误报：空数据回答允许提及待补指标但仍禁止串入其他 case 的具体数值；LLM judge 现在可见该 case 的 Twin / specialist 证据，不再把有来源的个性化数据误判为编造。
- Linux CI 的原 `s-u` 大分片连续两次在 `test_telegram_webhook.py` 完成后、进入 `test_timeline_agenda_lifecycle.py` 前停住；同命令本机 1090/1090 在 133.21 秒通过。为隔离进程级顺序污染且保持覆盖完整，将该分片拆成 `s`、`t[a-e]`、`t[f-z]+u` 三个独立 pytest 进程。第三次 run 中 `s` 和 `t[a-e]` 已通过，但新进程的 `t[f-z]+u` 仍超出 12 分钟；因此 Linux pytest timeout 改用可中断主线程的 `signal` 模式，该诊断分片开启逐测试输出，并为所有后端 shard 增加 20 分钟 job 上限，确保后续失败能给出具体栈而非无限等待。
- 营养目录部署补丁 focused regression：32 passed；`bash -n deploy.sh` 与全部 pre-commit hooks passed。
- Linux 全仓权威闸门：GitHub Actions run `29159958346` attempt 3 SUCCESS；四个首轮冻结分片均通过失败作业重跑恢复，最终 Backend tests enforcement 通过。
- 待执行：真机微信/小红书目标应用投递。Backend 全仓本地测试仍保留既有跨用例污染问题，Linux CI 为全仓权威闸门。
- 2026-07-12 上线前生产只读审计：近 30 天 116 条饮食记录中，AI 标记、图片、`food_id` 和新版饮食终态事件样本均为 0；因此当前不能宣称真实识别准确率或时延达标，需新 TestFlight/OTA 产生样本后再验收。
- T5.1 发布回归：Mobile 全量 `233 suites / 1626 tests`、受影响 focused `66 tests`、TypeScript 通过；Backend 饮食/营养/事件联合回归 `112 tests` 通过；lint `0 errors`（保留全仓 97 条既有 warnings）；pre-commit、doc drift 与 Dossier consistency 全绿。
- T5.2 发布前回归：Backend 识别清洗/营养校准/Diet API/Agent vision 联合 `74 tests` 通过；Mobile focused `24 tests` 与全量 `233 suites / 1626 tests` 通过；TypeScript 通过，OpenAPI 生成仅新增 4 行份量字段；lint `0 errors`（97 条既有 warnings）；带项目 venv 的全部 pre-commit、doc drift 与 Dossier consistency 通过。独立审查另以 RED 测试修复“益生菌酸奶”被补剂规则误删的假阳性。
- T5.2 首次 CI run `29164922239` 中 type drift 在补齐 Frontend 生成类型后通过，但 Linux `a-b` 分片连续两次远超历史绿灯的 4 分 23 秒，并在 `test_agent_health_manage.py` 与 `test_agent_intervention_cycle_tool.py` 边界失去输出；该边界组合本机 `30/30` 通过，`c-d` 重跑也在 3 分 36 秒通过。判定为既有进程级顺序污染而非饮食断言回归，将 86 个 `a-b` 测试文件拆为非 Agent、`agent_[a-h]`、`agent_[i-z]` 三个互斥进程；文件覆盖校验为 `86 -> 86`、差集 0。
- T5.2 CI run `29166225719` 验证上述三个新分片分别在 3 分 2 秒、2 分 15 秒和 1 分 24 秒通过；同轮旧 `t[f-z]+u` 分片在 69% 处进入 `test_twin_builder.py` 后冻结，并被 20 分钟上限终止，其他 16 个作业均通过。本机同命令 `392/392` 在 31.23 秒通过；据逐用例日志将其拆为 `t[f-v]`、`t[w-z]`、`u` 三个干净进程，原 24 个文件覆盖校验仍为 `24 -> 24`、差集 0。
- Linux 全仓权威闸门：GitHub Actions run `29163241845` SUCCESS；frontend、Mobile、macOS、type drift、backend quality、10 个后端测试分片及最终 backend enforcement 全部通过。

## G4 · 安全闸

- 触发：健康数据写入、AI 营养估算、私有图片和社交分享。
- 已落实：owner scope、确认/取消/清理行锁、真实 PostgreSQL 竞态证明、确认幂等、取消后正文擦除、草稿与正式记录图片失败可重试、SecureStore 用户隔离且非阻断、恢复前服务端 token 终态校验、编辑时 Mobile/Backend 双层 provenance 清理、分享前显式操作、分享产物去身份化和临时文件释放。
- 同一独立审查代理连续五轮核对；最后一轮未发现 P0/P1/P2。
- **裁决：PASS**。

## S6 · 部署

- 路由：backend deploy -> type sync -> TestFlight。因新增原生分享依赖，本版本不向缺少该模块的旧二进制发送 OTA。
- Backend 已从干净的 `origin/main` 完成第三次增量部署；最终生产 commit 为 `612de0bc54aa0b83f25ee4a116a0b161bc08820d`。
- 第三次部署前 PostgreSQL 备份：`/opt/health-app/backups/health_db_2026-07-12_02-27.sql.gz`，38 MB，权限 `0600`，完整性与 force-RLS 检查通过。
- TestFlight 构建：版本 `1.3.1 (221)`，EAS build `a6886f1c-d94f-4463-8a2e-90aeb12bce4c`；submission `4e54e7b1-1a9c-498c-8569-83deb950514a` 已成功上传 App Store Connect。
- production OTA：runtime `1.3.1`，update group `7a83e627-d87d-49df-8a83-de59c2867567`，iOS update `019f5272-ec99-760e-ad91-7097c018a0db`；EAS `update:view` 复核 branch、commit、runtime 与非回滚状态一致。

## G5 · 部署健康闸

- 生产受控迁移状态正常：`20260711_200000_create_diet_photo_drafts` 与 `20260711_201000_add_food_calibration_names` 已应用，本轮无重复迁移。
- 部署内营养目录 seed 明确输出 `6 food_items, 6 food_nutrients`；部署后只读 SQL 复核为 6/6，豆腐校准名仅 `北豆腐/老豆腐`，鸡胸肉校准名不含泛化“鸡肉”。
- `health-backend`、`celery-worker`、`celery-beat` 均为 active；部署健康分 `60/60 PASS`；skills manifest 本地/线上均为 22。
- 公网及服务器本机 `/api/v1/health` 均返回 healthy，API、PostgreSQL、Redis、Celery 全部 connected/running。
- T5.1 增量部署后 `health-backend` 为 active；公网 `/api/v1/health` 再次返回 healthy，production OTA 已绑定同一代码 commit。
- **裁决：PASS**。

## S7 · 上线验证

- iPhone 17 Pro 模拟器已验证照片确认、固定 1080x1440 分享图、系统分享面板与无重叠布局。
- Backend 生产迁移、营养目录、服务状态和公网健康检查已验证。
- TestFlight `1.3.1 (221)` 已成功上传 App Store Connect；Apple 处理完成状态尚未单独核实，因此不宣称当前已可安装。
- build 221 对应 runtime `1.3.1` 的 production OTA 已发布；设备冷启或后台超过 30 秒后可拉取。当前生产仍无新版终态样本，不宣称真实 p50/p95 或纠错率已达标。
- 待真机验证：相机实拍 -> 识别 -> 修正 -> 确认单次写入，以及分享图分别投递微信和小红书。

## G6 · 验证闸

- 模拟器与生产后端验证通过；真机目标应用投递尚缺证据。
- **裁决：PENDING**。保持 `device_validation_pending`，不进入完成态。

## S8 · 沉淀

- 决策 1：审核营养目录是校准链路的运行时前置条件，必须由标准部署幂等补齐，不能只依赖可选手工 seed。
- 决策 2：新增原生分享依赖必须发新二进制；旧二进制禁止接收会引用缺失原生模块的 OTA。
- 决策 3：社交分享验收必须覆盖目标应用真机接收，不以系统分享面板出现代替微信/小红书成功投递。
