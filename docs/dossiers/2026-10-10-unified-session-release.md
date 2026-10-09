# 跨 session 统一整合与发布

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 统一整合与发布验证 |

## G1 范围准入

裁决：PASS。用户明确授权实现后整合其他 session 并完成最终部署和发布。本次汇总既有个人周导航、健康只读导航、运行分析、每日建议 TokenPlan、仪表盘和环境展示、Workout 图表、照片份量回执与可信 OTA 目录修复，不扩大健康写权限或原生包发布范围。

## 固定来源与整合

个人周导航 e7ad64513、忙碌状态 6adc1de1b；Web/TokenPlan 汇总 c4c05120b；照片回执 5ccf5b9a6；远端主干和可信 OTA 修复由 8ba1df80b 正常合并；文档及地图 e1dac0239；CI 测试目录 19f748b13；跨账号缓存隔离 4952ee90c。原本未纳入的视觉验收文档保存在 Git stash，未覆盖或删除。其他 session 已交接并停止独立发布。

## G2 与 G3 本地证据

原功能规格及各 dossier 继续作为行为范围真源。统一数据库 CI-mode：349 passed、5 PostgreSQL 专项 skips；独立 PostgreSQL17 实际整合：283 passed；Mobile 全量：3370 passed、1 skip，TypeScript 通过；发布工具：219 passed、4 macOS 不适用 skips；Web 最终全量：513 passed、1 skip，TypeScript、lint 通过（既有 39 条 lint warnings 保留）。OpenAPI 双端生成类型检查、System Map 和 dossier consistency 通过。运行分析及导航新增模块已纳入正式 CI 选择器。

本地 Next 安装版本与锁文件不同，锁依赖完整验证以本次精确 SHA 的 GitHub CI 为准。独立审查发现旧账号创建、换号后发送的缓存污染，已补真实页面闭包与请求层失败回归后修复。独立 lifenav_readiness 对固定实现 SHA 4952ee90c 复核安全 GO，原缓存阻断解除；本记录仅补交付证据，不改变实现。

## G4 发布前闸

安全 GO，待精确 SHA 完整 CI。不得以本地检查替代。所有外接 LifeNav 开关继续关闭；没有接收方真实联调或七天使用证据。

## G5 与 G6 发布和现场验证

待执行后端可信发布、Web 独立发布和 iOS 可信 OTA 的 validate/publish；每次均绑定同一完整绿色 SHA，记录持久回执及公开健康检查。不得重跑已失败的旧 OTA 或使用旧包冒充候选。Mobile 模拟器现场仍有未验证项，当前未申请 App Store/TestFlight 发布。部署成功与真实用户流程验收分别记录。
