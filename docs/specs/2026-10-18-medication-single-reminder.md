# 用药单次提醒与 Agent 入口

## 准入与边界

用户要求：“用药提醒连续推送三次 只需要一次 且需要点击到agent对话页面”。这是既有提醒执行循环修复；HealthAgendaItem / ExecutionEvent，manual_request，范围为本人用药提醒，不增加模型处方或写自治。截图两条“吃药提醒”对应本地每日排程，一条“用药提醒”对应服务端；源码显示本地取消再重排未串行，且同一时间多药分别通知。

## 行为合同

- 服务端到点扫描为唯一新药域提醒生产者；停止 medication 提前 15 分钟路径及待发送副本。同用户、同一触发分钟的多药合并一条。显式 reminder_times 保持既有北京时间语义；缺少显式时点的活跃本人药物只从 day_schedule.scheduled 取得解算时点，并保持用户时区，排除 rejected/deferred/他人/补剂项。补剂原有预提醒和显式时点行为保留。不同用户、下一时点、下一日期不得合并掉。
- App 启动（包括未登录）和回到前台清理 kind=medication_reminder 的旧本地排程；dashboard 兼容入口只清理，绝不再创建本地通知。保留其它提醒。清理异常可见并在下一前台/刷新重试，不伪装成功。
- 服务端沿用配置、许可、去重、静默与隐私 choke point。锁屏不显示药名/剂量；组合通知无单药 TAKEN/SKIP 操作。
- PostgreSQL 独立连接持有 owner/date/time advisory lock，跨 PushService 提交保留；重复扫描按已持久化 owner/date/time rule_id 去重（含 owner 避免客户端切账号后消费标记碰撞）。获取或释放结果未知时丢弃连接，避免锁回池。
- 延迟出队用 delayed→pending 条件更新原子认领，避免两个 worker 从旧快照重复发送；不重发未知 pending。无 schema 变更。
- 新旧用药提醒（包括 pre_event medication）的普通点击和历史点击进入 `/(tabs)/chat`，预填日期、原始计划时间和只读核实问题；不携药名/剂量，不自动发送，不自动打卡。chat 的 context 会立即发送，因此此入口只传 prompt/badge/newChat/contextEntry，不传 context/autoSend。
- 缺日期旧本地通知明确“日期未确认”，不得默认为今天。非法值进入通用核实草稿。用户编辑并发送后沿现有健康 Agent 安全链路处理；新入口不把推送文字当作已核验健康事实。
- 用药管理页的专用确认页面仍保留；已到达的锁屏通知不冒充已撤回。关闭本地副本后提醒依赖服务端推送可达性，不新增离线备用生产者。

## 验证与交付

先复现重复/跳转失败再修复；覆盖合并、用户/时间隔离、重复扫描、PostgreSQL 双连接锁和双 worker 延迟认领、原文隐私、本地清理重试、普通点击不调用记录接口。同步 PostgreSQL CI 分片和地图；独立 G4 后才进入发布。当前 main 前置原生 GPS 候选、GitHub workflow 权限和锁屏断点沿现有发布记录处理，不用本地绿色替代精确远端 CI 或分发。
