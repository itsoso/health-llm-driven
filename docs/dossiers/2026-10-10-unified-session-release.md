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

## 首轮统一候选发布实绩

候选 ef64fb9d351ad955d4a37b2c55f1dc73c0f09e5e 的完整 CI 37964382737 attempt 2 全绿。首轮 live-change 检查要求本 SHA 的真实模型证据，补齐后仅重跑失败 CI：62 个离线场景、5 个在线场景通过，10 次 API 计费审计调用全部成功，未发现基线退化。未关闭或放宽 Gate。

可信 validate 37966219466 成功。首次授权轮换漏执行旧授权退休，库存预检查拒绝；未产生 intent、归档、新工作区或业务租约。独立复核允许补齐前置后继续：canonical revoke 旧身份、核对公钥后销毁旧 loopback 私钥、保留原失败日志及成功终态/锁身份，再安装新 SHA 授权。首次失败日志摘要 f806f341c6f977f911223d6386dce5d1dacbe640a8fb2b9834f57d60a20a6f6b 原样保留。

后端 Trusted release 37967680330 attempt 2 成功（首次在访问生产凭据之前因 GitHub 元数据读取失败停止，未消费部署）。服务器 completed.json 精确 SUCCEEDED、生产 HEAD 精确候选、健康度 60/60、四个服务 active、内网 /health 和公网 /api/health 200，新个人/健康导航未登录均 401；发布租约释放。

Web 独立操作 86cb1a54961245c789cc89e4204cbcff 生成 FRONTEND_SUCCEEDED，前端树 4dd6ebaa2fa84e1b009354f60c47edfa88a07153、制品摘要 79b77fe2592a02910c34c86d163c15fc8546890aeb1740b5f6f16ac3c6ac9da6。锁定依赖的实际 Next 生产构建及内外网 privacy/connect 页面核验通过。实际已登录 Chrome 复验：环境 404 恢复；个人工作区读取 revision 0 并切换周计划；仪表盘手动卡片、趋势坐标轴及非空 SVG 路径；运动详情非空心率区域曲线。生产未新增测试任务或修改健康记录，现场截图只保存在临时目录，不提交健康载荷。

OTA validate 37969771532 成功，canonical 目录/ACL 问题已解除。publish 37971203861 在 publication 阶段阻断：服务器 ota/<sha>、claim、租约均不存在，GitHub audit artifact 数量 0，没有可恢复的 vendor receipt。不得把泛化日志或短耗时推定为具体根因，不重跑此失败 run，也未执行第二次 vendor update。现有发布器把 claim 前阶段异常全部泛化且不归档安全诊断；本次继续补充闭集诊断和无 export/claim/update 的只读供应商准入，保留全部安全 Gate，修复后的候选需重新审查和 CI。Mobile OTA 发布尚未完成。

诊断改进先取得失败测试，再完成实现；新鲜发布工具验证 195 passed、1 macOS Linux ACL 不适用 skip。独立 ota_diagnostic_review 对四个固定文件摘要裁决 G4 GO。validate 现在包含受既有源码和精确 CI 闸保护的认证只读供应商准入；未增加发布次数或放宽单次 claim/回执恢复规则。下一候选须先完整 CI，再执行该只读诊断，确认前置条件后才部署和发布。
