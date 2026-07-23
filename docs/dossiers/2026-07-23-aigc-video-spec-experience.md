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
  - Backend AIGC 定向回归：93 passed。
  - Mobile 卡片回归：65 passed。
  - TypeScript：`tsc --noEmit` 通过。
  - System map 与 doc drift：通过。
- G4 安全：PASS
  - 客户端只能选择服务端白名单时长，不能替换 prompt、model 或 source。
  - 最终规格进入请求指纹；重复确认仍返回同一任务。
  - 运维聚合不记录 prompt、媒体 URL 或健康正文。
- G5 部署健康：PASS
  - Backend 已从干净提交 `dc4dd70bb217` 部署。
  - 部署健康分 `60/60`，Skills manifest `22/22`。
  - 生产代码已包含 5/10/15 秒选择、规格冻结、幂等和任务监控；主干后续提交仅包含文档变更。
- G6 上线验证：PARTIAL
  - production OTA 已发布，runtime `1.3.2`。
  - Update group：`68153270-72d1-48d9-8866-dbbd976c8721`。
  - iOS update：`019f8f31-cfe0-7129-bedc-7e8ac12b100a`。
  - 待真机冷启动应用更新后，完成 5/10/15 秒选择、重复确认幂等、生成状态和播放烟测。

## 后续边界

- HappyHorse 原生单任务最大 15 秒，本轮没有伪造 16 秒能力。
- 16 秒需要独立的父子任务、片段连续性、合成、失败恢复和成本预算设计，后续另立 Dossier。
