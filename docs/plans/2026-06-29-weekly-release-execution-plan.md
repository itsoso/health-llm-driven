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

## 第六批实现切片

P0/P1 Mobile 阿衡人格主路径收敛已推进:

- Chat header / 模型选择器 / 空态提示 / starter chip 无障碍标签统一为 `阿衡`。
- Chat 单条回复分享、对话节选分享、AI 分享正文尾注统一为 `阿衡`。
- 菜单分享动态卡片的分享尾注统一为 `阿衡`,并新增纯文本 helper 回归测试。
- 首页 `HomeCommandCard` 顶部人格和“问原因”无障碍标签统一为 `阿衡`。
- 底部 Chat tab 已进一步收敛为“阿衡,与健康参谋对话”。

## 第七批实现切片

P0 Mobile Shell 品牌一致性已推进:

- 新增 `APP_DISPLAY_NAME = '阿衡'` 品牌常量,供高可见 shell surface 复用。
- 登录页标题从 `HealthPilot` 收敛为 `阿衡`。
- 根布局锁屏抽成 `AppLockScreen`,锁屏态显示 `阿衡` 并保留解锁回调。
- Settings 的 Siri 语音记录示例从 `HealthPilot` 收敛为 `阿衡`。
- 非测试代码扫描 `mobile/app mobile/components mobile/utils` 不再命中 `HealthPilot`。

## 第八批实现切片

P1/P2 Rokid 俯卧撑教练旧称收敛已推进:

- `Rokid 俯卧撑计数` wrong CXR session mode 提示从“完全退出 Reva”收敛为“完全退出阿衡”。
- 同一提示从“不要先打开 Reva 眼镜视图”收敛为“不要先打开阿衡眼镜视图”。
- 复用 `APP_DISPLAY_NAME`,不新造产品名常量。
- 保留 `Rokid` / `CXR-L` / `CustomView` / `CustomApp` / native package / URL scheme 等技术名。
- `Rokid Health` 大页仍作为后续独立切片,避免把 SDK 状态机和大测试面混入本批。

## 第九批实现切片

P1/P2 Rokid Health 大页旧称收敛已推进:

- `Rokid 眼镜健康模式` 大页的授权等待、CustomView 打开/等待/失败、语音控制 title、页面按钮和用户诊断指引统一为 `阿衡`。
- 眼镜端 CustomView 展示 payload 从 `Reva Health` / `Reva 语音控制` 收敛为 `阿衡 Health` / `阿衡语音控制`。
- 复用 `APP_DISPLAY_NAME`,不新造产品名常量。
- 保留 `openRokidRevaCustomView` / `createRokidRevaCustomViewLayout`、`appName: 'Reva'`、`Reva build`、`appName=Reva` 等技术函数、SDK auth 字段和历史诊断字段。
- 不改 Rokid 设备控制、语音、拍照、记录写入和权限逻辑。

## 第十批实现切片

P0 App Store 高可见审核叙事闸已推进:

- `check_app_store_release_pack.py` 新增 release narrative gate,覆盖 submission pack、review notes 和 screenshot runbook。
- 旧的用户可见叙事词 `Reva`、`复元`、`健康助理`、`守护神` 进入 App Store 高可见文案时直接失败。
- App Store 文案必须包含当前底部导航 `今日 / 阿衡 / 记录 / 我` 或等价中文顿号写法。
- App Store 文案必须包含当前定位词 `健康参谋`。
- `submission-pack.md` keywords 从 `健康助理` 收敛为 `阿衡` / `健康参谋`。

## 第十一批实现切片

P0/P1 Mobile 底部导航命名收敛已推进:

- 用户确认采用方案 1:`今日 / 阿衡 / 记录 / 我`。
- `chat` route 和技术文件名不改,只改用户可见 tab label 和 accessibility。
- `私教` 作为旧用户可见 tab 文案进入 App Store release narrative gate 的 stale term 列表。
- App Store submission pack、review notes、screenshot runbook 和 system-map/mobile 产品地图同步为 `阿衡`。

## 本周不做

- 不把 App Store 发布伪装成已完成:缺 demo account、ASC credentials、人审截图时必须停在 pending。
- 不做处方、剂量、诊断承诺。
- 不做大范围技术符号重命名,避免破坏构建和历史文档。
- 不把 IoT、补剂下单、供应链自治作为本周上架卖点。

## 后续顺序

1. 补最终截图/审核材料路径,明确哪些需要用户提供。
2. 继续 Daily Artifact 主屏视觉走查和点击动线截图。
3. 继续 Chat card action 成功后的局部刷新/跳转反馈和记录页联动。
4. 视签名条件推进 Watch 真机和二维码发版。
