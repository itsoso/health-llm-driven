# Dossier: AIGC 短视频规格与生成体验

| 字段 | 值 |
|---|---|
| slug | `aigc-video-spec-experience` |
| 创建日期 | 2026-07-23 |
| 当前阶段 | S8 上线验证 |
| 状态 | deployed_device_smoke_pending |
| 负责 | Codex |
| 反馈环 | backend deploy + mobile OTA |

## S0 · 用户需求

> AIGC能到16秒吗 分析其他优化点
>
> 可以 按照你规划实施

- 谁用：在小巴 Agent 对话中创建健康行动短视频的 Mobile 用户。
- 解决什么：确认前看不到视频规格，生成过程状态粗糙，结果与运维指标不足。
- 当前绕过：用户只能接受 Agent 默认的 5 秒、9:16、720P 任务，生成后才知道结果。

## S1 · Discovery

- HappyHorse 1.1 单任务时长为 3–15 秒，当前后端与工具校验已正确限制。
- 草稿记录已持久化时长和比例，任务指纹也包含二者，具备安全扩展基础。
- Mobile 确认卡未展示或选择时长；任务卡只展示通用进度。
- 任务结果只投影媒体类型和 URL；运维已有状态、模型和错误聚合，但缺少时延和体积。
- 16 秒必须通过父子任务与合成实现，不应伪装成单任务参数。

## G1 · 准入裁决

- first_class_objects：AIGC confirmation、AIGC media job、Agent Run。
- core_loop_step：用户请求 → 明确规格 → 人工确认 → provider 执行 → 私有结果与回执。
- target_surface：Backend 为真源，Mobile 为日常确认与播放 surface。
- safety_level：中等成本与隐私风险。
- autonomy_tier：`manual_confirm`。
- smallest_end_to_end_slice：5/10/15 秒选择、规格冻结、状态展示、延迟监控。
- **裁决：PASS**。用户已明确批准实施。

## S2/S3 · Quick Flow Tech Spec

1. 建立模型能力注册表，单一声明时长、比例、分辨率和音频能力。
2. 确认时只允许覆盖安全白名单内的时长；提示词、源图片和模型继续由服务端绑定。
3. 将请求规格写入现有任务 JSON 元数据，不新增数据库迁移。
4. Mobile 确认卡展示并选择 5/10/15 秒；任务卡展示时长、比例、分辨率和阶段。
5. Mobile 轮询采用退避；服务端继续用租约限制真实 provider 查询。
6. 运维增加任务类型、生成时延和输出体积聚合，不包含 prompt 或媒体 URL。

## G2 · 可行性与安全压测

- 不放宽 15 秒服务端上限。
- 客户端不能修改 prompt、model 或 source。
- 时长覆盖先通过模型能力校验，再原子消费确认记录。
- 幂等指纹按最终冻结规格重算；重复点击仍至多产生一个付费任务。
- **裁决：PASS**。

## S4 · 研发任务

- [x] T1 模型能力注册表和请求规格持久化。
- [x] T2 确认 API 的受控时长选择与幂等测试。
- [x] T3 Mobile 确认卡、任务卡和轮询退避。
- [x] T4 运维时延与输出体积指标。
- [x] T5 后端、Mobile 测试，部署与 OTA。

## Gate 状态

- G3 测试：PASS
  - 原功能 Backend AIGC 定向回归：93 passed。
  - 过期确认与断流恢复 Backend 定向回归：53 passed。
  - Mobile 卡片回归：70 passed。
  - Web 卡片回归：38 passed。
  - Mac 确认恢复回归：5 passed。
  - Mobile / Web TypeScript：`tsc --noEmit` 通过。
  - Mobile design-token gate：通过。
  - System map 与 doc drift：通过。
  - Main CI：`43/43` jobs 通过，0 failure。
- G4 安全：PASS
  - 客户端只能选择服务端白名单时长，不能替换 prompt、model 或 source。
  - 最终规格进入请求指纹；重复确认仍返回同一任务。
  - 运维聚合不记录 prompt、媒体 URL 或健康正文。
  - Mobile 生产依赖审计：0 vulnerabilities；CI 发现的 PostCSS 高危公告已通过 `8.5.22` 安全补丁关闭。
- G5 部署健康：PASS
  - Backend 已从干净提交 `3da3fb92abf5` 部署。
  - 部署健康分 `60/60`，Skills manifest `22/22`。
  - 数据库备份、231 张表恢复演练、force-RLS 数据校验与站外加密归档均通过。
  - 生产 `health-backend.service` 为 `active (running)`，远端版本核验通过。
  - 生产代码已包含 5/10/15 秒选择、规格冻结、幂等、任务监控和过期确认恢复。
- G6 上线验证：PARTIAL
  - production OTA 已发布，runtime `1.3.2`。
  - Update group：`2208d1eb-facc-4d87-a0f7-0e4bf382f193`。
  - iOS update：`019f9006-e9a1-7c74-9140-fba1f4b1a3c4`。
  - OTA commit：`3da3fb92abf5282eb3cd24748b5b7404bb3840c7`。
  - 待真机回到前台应用更新后，点击原过期卡一次，验证重新确认、单一任务卡、无假失败、生成状态和播放。

## 2026-07-23 · 过期确认与断流恢复

### 事故

- 对话中的创作卡会长期保留，但服务端确认记录只有 10 分钟有效期。
- 用户约 75 分钟后点击旧卡，Mobile 未读取服务端返回的 `expired` 状态，连续提交 10 次均收到 `409`，界面只显示“提交未完成，请稍后重试”。
- 生产日志与只读账本确认没有创建任务、没有调用 provider、没有产生付费请求；失败发生在确认状态校验阶段。

### 修复

- 新草稿确认有效期改为 24 小时；24 小时恢复窗口内的旧草稿允许用户以一次新的明确点击重新确认。
- 重新确认继续使用确认 ID 派生的业务幂等键，并通过数据库原子 claim 保证至多创建一个付费任务。
- `dispatching` 成为 30 秒数据库租约；若进程在创建任务前退出，租约到期后可恢复。若任务已经持久化，则优先按幂等键恢复并补写确认回执。
- Mobile / Web 首次展示读取 owner-scoped 确认账本；过期、不可恢复和提交中状态均有明确界面。
- Mobile / Web 对提交响应丢失执行有界账本核对；任务已创建时直接切换任务卡，不再显示假失败，也不重复提交。
- Mac 在提交响应失败后同样读取确认账本并恢复已创建任务。

### 不变量

- 同一确认 ID 至多创建一个付费任务。
- 客户端超时、切后台或响应丢失不会把已创建任务显示为失败。
- 过期确认不会无限恢复；超过 24 小时必须重新发起创作。
- 轮询有固定次数上限，不形成无界请求。

## 后续边界

- HappyHorse 原生单任务最大 15 秒，本轮没有伪造 16 秒能力。
- 16 秒需要独立的父子任务、片段连续性、合成、失败恢复和成本预算设计，后续另立 Dossier。

## 2026-07-24 · 创作意图单任务收口

### 用户问题

- 用户请求“根据今天的活动、饮食和睡眠生成短视频”时，创作确认卡之外还出现“今日饮食”卡。
- 确认卡把第三方传输提示放在首屏主位置，但没有先说明将生成什么，用户难以核对任务。

### 根因

- Backend 已把明确的 AIGC 创作轮次限定为 `draft_aigc_media`，没有读取饮食卡的工具竞争。
- Mobile 的本地卡片兜底只按“饮食”等名词匹配，没有区分“查询饮食”和“把饮食作为创作素材”，因此与服务端权威创作卡竞争。

### 修复与不变量

- Mobile 在本地卡片分发边界识别“创作动作 + 媒体类型”，创作请求不再投影饮食、睡眠等本地查询卡。
- Backend 只从允许列表提取“活动、饮食、睡眠、补水、用药提醒、健康计划”等类别，生成确认预览；不回显具体步数、热量、睡眠分数、药名或完整 prompt。
- 确认卡先展示任务内容和视频规格，再展示第三方处理说明；付费生成仍需一次明确点击。
- 历史确认卡缺少新预览字段时继续兼容渲染。

### Gate 增量证据

- G3 测试：PASS
  - Mobile 卡片完整回归：71 passed。
  - Backend Agent/AIGC 链路：113 passed。
  - Mobile TypeScript：`tsc --noEmit` 通过。
  - Mobile lint：0 errors；仅仓库既有 warnings。
  - Python 编译检查与 `git diff --check` 通过。
- G4 安全：PASS
  - 原始健康数值和完整创作 prompt 不进入确认卡数据。
  - Provider 披露保留；确认前不创建付费任务。
- G5 部署健康：PASS
  - Backend 已从干净提交 `5560884448ac` 部署。
  - 数据库备份、231 张表恢复演练、force-RLS 完整性检查与站外加密归档均通过。
  - 部署健康分 `60/60`，Skills manifest `22/22`，远端版本核验通过。
- G6 上线验证：PARTIAL
  - production OTA runtime `1.3.2`。
  - Update group：`44f8f40c-cb3f-4ee8-8bfb-e8192d526cc5`。
  - iOS update：`019f9282-15dd-76d9-9db5-3f6a402ca85b`。
  - OTA commit：`5560884448ac477afb73495b003fb10ae8a82bd6`。
  - 待真机冷启动应用更新后，用“根据我今天的活动、饮食和睡眠生成短视频”验证：只出现一张创作确认卡、内容预览无具体健康数值、确认后只创建一个任务。

## 2026-07-24 · 视频时长选择收口

### 用户问题

- 当前确认卡没有产品约定的 `5/8/15` 秒选择。
- 新卡和历史卡都需要显示同一组真实可执行选项。

### 根因与决策

- Backend 模型能力注册表和 Mobile 历史卡回退仍固定为 `5/10/15`，因此 8 秒不会出现。
- 已持久化的旧卡还携带 `5/10/15`，只修改服务端无法立即修复历史对话。
- HappyHorse 单任务原生范围仍为 3–15 秒；本轮不伪造 16 秒能力。
- Backend 权威选择集改为 `5/8/15`。Mobile 将缺少选项或旧 `5/10/15` 集合迁移为 `5/8/15`；旧 10 秒草稿回落到 5 秒，已生成的 10 秒历史任务不受影响。

### 不变量

- 16 秒继续在 API 与服务层被拒绝，不会产生付费任务。
- 用户手动选择 8 秒后，异步确认状态刷新不得覆盖该选择。
- 最终时长进入确认请求、请求指纹、Provider 参数和任务规格回执。
- 历史卡不需要重新发起对话即可看到当前选择集。

### Gate 增量证据

- G3 测试：PASS
  - Backend AIGC/Kernel 定向回归：67 passed。
  - Mobile 卡片完整回归：72 passed。
  - Mobile TypeScript：`tsc --noEmit` 通过。
  - Mobile lint：0 errors；仅仓库既有 warnings。
  - Mobile design-token gate：通过。
  - Python 编译、system-map/doc drift 与 `git diff --check`：通过。
- G4 安全：PASS
  - 客户端仍不能修改 prompt、model 或 source。
  - 服务端原生时长上限保持 15 秒。
- G5 部署健康：PENDING。
- G6 上线验证：PENDING。
