# 设置与更多操作：返回路径修复

| 字段 | 值 |
|---|---|
| slug | mobile-menu-return |
| 日期 | 2026-10-12 |
| 当前阶段 | G6 PASS，实现已发布 |
| 状态 | shipped |
| 负责 | root |

## G1 准入

裁决: PASS。用户明确要求修复设置/更多操作与安全入口的返回链路，保持认证、同意与所有健康写入边界。

- 用户证据：设置与聊天更多操作截图；“安全点击之后无法回到主界面”，要求走查同类问题。
- 范围：本地 Mobile 导航与菜单实现。发布 owner：优化 README（01a120c7-1ba0-75c3-9487-447bd5bfa28f）。本线程不暂存、commit、push、deploy 或 OTA。
- 流程：quick_fix + safety；未启用 superpowers。

## 原因与实现

- alerts 与 journal 是隐藏 Tab；底部导航移除后仍无可见出口。复用 BackToChatBar，加载与空列表时也能返回 chat；安全告警页标题与菜单入口一致。
- me 复用 settings 时根据 canGoBack 判断页面身份，Tab 历史会让它误走上一页。me 显式传 home，固定返回 chat；独立 settings 保持正常上一页与无历史兜底。
- backOrChat 统一栈页面的无历史出口：有历史 back，无历史 replace chat。覆盖账号安全、通知、用眼、语音风格、隐私政策、家庭、硬性指令、数据自检、饮食、语音会话退出、推理回放列表与详情、案例详情。
- 案例/决策详情的加载态新增可点击返回；记录缺失时保留兜底。
- 设置把家庭、日记、硬性指令、数据自检归入健康管理。更多操作按功能分组，安全区内限制宽高，内容可滚动，关闭按钮固定于菜单顶部且点击区域至少 44pt。
- 不改变密码提交、AI consent、健康数据写入、语音记录确认或 reset 清理顺序。

## 本地验证

- RED：最初 menu-return 4 例失败（无出口/无可访问返回按钮）；me 历史与更多菜单滚动 2 例失败；详情加载出口另 2 例失败。
- GREEN：menu-return、settings、dietCapture、family、menu-router 5 套共 97 例通过；chat 73 例通过。合计 170 例。
- menu-router 使用真实 Expo Router / Tabs，覆盖 settings → alerts/journal → chat、账号安全正常返回 settings、冷链接返回 chat；根 Stack 对 settings/account-security 使用与生产一致的 modal 配置。
- Jest 增加 decode-uri-component 转换支持，避免真实路由依赖的 ESM 模块无法加载；没有 mock 路由状态机。
- TypeScript noEmit、git diff --check 通过；settings 路由文件存在性检查通过。
- 独立 safety 文件预审及详情/语音增量预审均 GO；不是固定 SHA G4。
- 期间 chat 的 3 个模型入口测试因并行管理员权限改动失败，已协调 owner 更新对应身份 fixture，随后 chat 全部通过；保留 owner 的修改。

## 交付边界与接力

- 真实路由测试仍在 React Native 测试运行器执行，不冒充 iOS 原生 modal 转场、小屏滚动或模拟器视觉验收。本地交接时未验收新候选模拟器包，最终范围见下方交付记录。
- System Map 只读检查发现路由计数漂移（me 从 re-export 改为显式组件）；未手写计数。已两次协调 owner，生成物由统一 owner 接管，避免共享工作树并行生成覆盖。
- 发布需 owner 统一同步生成物、固定候选 SHA 独立 G4、完整 CI、对应后端与 OTA 闸；本地交接时没有上线回执，最终发布见下方记录；没有OTA操作。
- 未读取秘密或原始用户健康数据；未为测试触发生产读写、外部模型或设备权限授权。

## 验收清单

1. 更多操作 → 个人中心与设置 → 安全告警 → 返回小巴，回到原聊天主界面。
2. 健康日记及案例详情在加载、空/缺失记录、正常列表情况下均可退出。
3. 账号安全从设置打开返回设置，直接打开时返回主界面；不会触发保存。
4. 多次个人中心/告警往返不会按旧 Tab 历史循环。
5. 窄屏、横屏、大字体下更多操作末项可滚动到达；关闭按钮可点击，删除仍经过原确认流程。

## 统一 owner 最终交付

实现已纳入55dad9b3c后端/Web发布及e580383da原生1.3.5(278)。固定候选独立G4、精确绿色CI、本地CI-mode、实际签名/来源/公开完整IPA摘要及模拟器三次启动横屏验证通过；详细SHA、回执、保留失败和未覆盖项见[统一发布dossier](2026-10-12-daily-draft-admin-model.md)。原本地预审与接力边界记录保留为历史，不是当前未发布声明。没有OTA或TestFlight操作。

安装页：[1.3.5(278)](https://health.executor.life/mobile-install/ios/20261012-admin-model-e580383da-278/install.html)。登录后原生业务路径、真实用户截图原始故障与真机安装/硬件未验证；组件、真实路由或Axios transport测试不能冒充这些验收。发布实现不保证截图原始网络/会话原因已经确定。
