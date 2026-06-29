# 2026-06-29 本周执行计划:阿衡可用发布版

> 周期:2026-06-29 至 2026-07-05。
> 目标:下周可发布一个用户可用、UI 统一、核心动线清晰、具备 App Store 上架条件的阿衡版本。
> 方法:基于 `docs/PRODUCT_ROADMAP.md`、`docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`、`docs/plans/2026-06-27-reva-mobile-watch-healthkit-experience-plan.md` 和 `docs/dossiers/2026-06-28-app-store-mvp-release.md` 排序。

## 本周判断

当前系统不缺更多健康功能。最影响发布和留存的是四件事:

1. 发布材料和 App 内用户可见命名必须一致。
2. Mobile 第一屏必须围绕“今日状态 + 今日最重要行动”形成日常主线。
3. Chat 动态卡片和快速记录必须成为主路径,而不是隐藏能力。
4. Watch / HealthKit 要先证明低摩擦采集和执行,不承诺平台做不到的“表冠长按第三方说话”。

## 优先级

| 优先级 | 本周事项 | 依据 | 本周验收 |
|---|---|---|---|
| P0 | App Store 发布一致性闸 | `submission-pack.md` 已改为阿衡,但代码仍可能残留旧名 | `mobile/app.json`、`CFBundleDisplayName`、动态 config、release checker 都锁定阿衡 |
| P0 | 截图 / demo / 审核材料最终闸 | App Store dossier 仍 pending demo screenshot、ASC 凭证、人审 | ready 截图集过 `check_app_store_release_pack.py`;不能自动完成的项明确留人审 |
| P1 | Mobile Daily Artifact / 健康日序主线 | Roadmap H1:每日工件先于更多 specialist | 首页只突出一个 top action,带证据、freshness、完成/跳过 |
| P1 | Chat + 动态 UI 卡片融合 | 用户要求 Chat + 动态卡片;代码已有 card registry | Chat 中可见记录/复盘/运行时卡片,action 走 manual_confirm |
| P2 | HealthKit 前台自动同步与新鲜度 | 数据底座优先;后台 HK 非本周必投 | 回前台自动 best-effort 同步,冷却去重,失败不阻断 |
| P2 | Watch 低摩擦记录与短答 | watch 已编译,真机/签名是长杆 | 先保留记录能力和短答安全门;真机/EAS 作为异步发布里程碑 |
| P3 | 5 分钟 on-ramp / 异质用户验证准备 | 10M 路线要求第 2 个用户可用 | demo 数据和示例报告路径进入计划,不污染真实 Twin |

## 第一批实现切片

本批先做 P0 发布一致性闸:

- 把用户可见 App 名锁定为 `阿衡`。
- 保留 `HealthPilot` 作为工程/技术历史名,不重命名 Xcode target、bundle id、脚本路径。
- 增强发布检查:若 Expo app name、`CFBundleDisplayName` 或 App Store submission pack 回退到旧名,测试和 release gate 必须失败。

## 第二批实现切片

P0 App Store final-submit gate 已完成:

- 普通 `check_app_store_release_pack.py` 继续用于无人工凭证的日常回归。
- `check_app_store_release_pack.py --final-submit` 用于真正提交前,强制检查 App Store-ready 截图、demo account/password 和 ASC credentials。
- 当前 final-submit 预期失败,阻塞项是用户提供 demo credentials、ASC credentials 和最终截图目录。

## 第三批实现切片

P1 Mobile 阿衡人格文案收敛已完成:

- 首页 Daily Artifact 的 ask action、首页试用入口、`/reva-onboarding`、`/reva` hub、Chat 体检导入动态卡片统一为 `阿衡`。
- 语音分享、家庭邀请、体检导入权限、聊天附件权限、运动分享、隐私政策、分享落地页等通用用户可见文案统一为 `阿衡`。
- 技术符号、历史组件名、route 名和 Reva design token 暂不重命名。
- Rokid 专页旧称保留为后续独立切片,避免外设 SDK 文案和大测试面混入本批。

## 第四批实现切片

P1/P3 快速记录入口已推进:

- `/(tabs)/record` 高频记录区新增 `俯卧撑`。
- 点击直达 `/rokid-pushup-coach`,复用已有本地/眼镜计数与保存能力,不新增后端 schema。
- `更多记录 -> 运动` 保持为 `/workout-list`,用于查看历史运动记录。

## 第五批实现切片

P1 Chat 动态卡片 action 安全可见性已推进:

- 多卡 `cards_group` 子卡 action 已有回归测试,确保运行时/复盘等多卡回复仍可点击。
- `route.open` 导航 action 保持可见。
- `agenda.complete` / `write_intent.confirm` / `write_intent.dismiss` 等写动作必须带 `requires_manual_confirm=true` 才展示给用户。
- 服务层 `dispatchChatCardAction` 仍保留 fail-loud,不放宽 endpoint allowlist。

## 本周不做

- 不把 App Store 发布伪装成已完成:缺 demo account、ASC credentials、人审截图时必须停在 pending。
- 不做处方、剂量、诊断承诺。
- 不做大范围技术符号重命名,避免破坏构建和历史文档。
- 不把 IoT、补剂下单、供应链自治作为本周上架卖点。

## 后续顺序

1. 补最终截图/审核材料路径,明确哪些需要用户提供。
2. 继续 Daily Artifact 主屏视觉走查和点击动线截图。
3. 继续 Chat card action 成功后的局部刷新/跳转反馈和记录页联动。
4. 单独处理 Rokid 专页旧称和相关测试。
5. 视签名条件推进 Watch 真机和二维码发版。
