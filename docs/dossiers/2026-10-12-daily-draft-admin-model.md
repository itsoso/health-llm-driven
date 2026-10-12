# Dossier: 日常安排误报与管理员模型入口

| 字段 | 值 |
|---|---|
| slug | daily-draft-admin-model |
| 日期 | 2026-10-12 |
| 当前阶段 | G6 PASS，已发布 |
| 状态 | shipped |
| 负责 | root |

## G1/G2

裁决: PASS。用户截图“规划今天饮食运动和睡眠”反复出现通用查询失败，并要求优化性能、模型下拉只对管理员开放且不出现tokenplan。准入见 docs/specs/active/2026-10-12-daily-draft-admin-model.md。复用当前输入建议scope，闭合请求只允许通用知识；不新增个人读取或计划写入。管理员模型权限同时覆盖Mobile/Web、API、偏好provider、图片和工具门控consumer、per-request extra_context；当前数据库角色是授权真源。

## G3

实际截图原话先5 failed/7 passed，修改后Pi/panel均单轮完成、无个人工具、不误入睡前固定答复。个人依据、他人、取消、写入和未知尾句负向边界保留严格策略。权限RED首次fixture缺name/独立旧模块加载缺测试env，保留配置错误，不当行为证据；补齐fixture/env后旧API真实403约束失败。Mobile/Web成员缓存options和tokenplan RED均2例失败；实现后Mobile Picker/Header11例、Chat合计84例、Web5例通过，两端tsc通过。后端邻近232例230 passed/2 skipped；覆盖全部模型consumer的追加73例通过。PG第一次cluster错误使用ASCII编码，9个fixture错误；UTF8新集群19 passed、shutdown exit0，真实权限join与Pi/panel路径通过，旧错误日志保留。不得把本地单轮当成实际线上总延时。

## G4

补selftest在provider前拒绝及管理员降权后所有consumer测试。360/42/55固定候选及e580原生增量均取得独立GO；55独立468项后端、71项包摘要测试通过，e580独立47项配置测试、类型检查及实际IPA签名/双方向键审核通过。原NO-GO与CI失败仍保留。

## G5/G6

本批Backend/Web实际发布SHA为55dad9b3c，原生包为e580383da，后端与Web代码树在两版完全相同，独立兼容性审查通过。拍照路由等待修复a75已包含在55，但实际拍照延时仍未验证。菜单返回与AI consent只读恢复的明确交接已整合，无关benchmark实验保留。OTA原生基线不兼容，按原生扫码安装方式交付。

## CI 断点

360bf9f6a完整CI的docs-quality阻断：G1缺机器可识别的裁决前缀、菜单交接dossier缺状态/阶段与G1。补齐真实裁决与字段，不降低检查，不覆盖原运行。360的私有安装包不能作为通过CI的交付候选。

## 全量回归断点与修正

42f76adb0完整CI发现8个正向模型选择场景的旧fixture仍使用普通账号。仅将这些明确测试手动模型选择/模型变体的合成账号标成管理员，不改断言，也不全局提升共享fixture；相关5组468例全部通过，成员拒绝和降权负向测试保留。

本地CI-mode首轮同步点未在45秒内到达、之后实际出现；原测试单独重跑7.86秒通过，保留原失败且不放宽超时。串行完整闸另发现部署包摘要比较包含atime，读取本身可能被误判变化，而os.stat_result的秒级tuple比较可能漏纳秒修改。两个新回归先RED（2 failed），改为比较inode/dev、mode、uid/gid、nlink、size与mtime_ns/ctime_ns，排除只读访问时间；71项Neo部署负向/隔离检查通过，保留内容、替换、权限、链接和大小边界。不启用或部署Neo桥接。

运维包装独立审查补强原锁不可重建、撤权/私钥删除前的完整历史校验与安装executor pin，以及当前live内容校验；封存且已验证的非活动旧备份仍按既定治理跳过正文。全部NO-GO、原失败回执与日志保留；第四次全新静态审查GO，外部操作还须最新精确CI/本地闸通过。

## 原生验收断点

55dad9b3c 完整 CI 38190518789 绿色，本地 CI-mode 3595 passed、22 skipped、84 subtests passed；后端部署 38191974216 成功，生产 clean SHA 55、四服务 active、公开 health 200 healthy。Web 使用独立 frontend publication，不能把后端成功当 Web 生效。

私有 1.3.5(278) IPA 来源55、独立签名/摘要/iPad配置检查通过，尚未分发。首轮模拟器横屏断言通过，但补采截图及后续启动出现旋转不生效，全部失败与原 xcresult 保留，不豁免。构建依赖 ExpoAppDelegateSubscriberManager 的运行时读取 `UISupportedInterfaceOrientations~pad`，缺失时退回通用 portrait；UIKit标准键 `~ipad` 静态正确不能证明运行时支持。新增4项配置回归先失败，修复后47项通过、Mobile tsc exit0；仅iPad增加与标准键相同四方向的Expo兼容键，所有非iPad variant清除两键并保持通用portrait。不改依赖、权限、签名或健康数据授权。

该原生修复需要新候选精确 CI、独立制品审核及首轮/重新启动旋转验证后重新打包；不能通过OTA。后端与Web树若同55，沿用各自实际55成功回执，不重复部署。真实注册设备安装、相机与登录后原生业务UI未验证；不能以合成组件/路由回归或登录页截图冒充这些验收。

## 最终发布与验证

- Backend：55dad9b3c，精确CI 38190518789、部署38191974216成功；生产对应clean SHA、四服务active、公开health200 healthy、业务lease不存在。
- Web：同55，独立publication `feb120034c964e9a87a00f0e1ccebdaf` 为FRONTEND_SUCCEEDED；完整frontend tree `58e56fbb0df1716ca237e93f4c84922fc3a61a38`，助手/隐私/连接页面公开回读200。
- Native：e580383da，精确CI38193333474成功，fresh本地CI-mode3595 passed、22 skipped、84 subtests passed；1.3.5(278)实际签名与来源回执通过独立审核，~pad/~ipad同4方向、通用portrait、family[1,2]、fullscreenfalse。连续3次真实模拟器app launch均能旋转到1376×1032，密码控件可操作，6张完整屏截图保留；不将它当登录后业务流程或真机验收。
- 分发首次在legacy latest目录保护预检停止；独立只读确认目标目录未创建、无远端上传副作用后，受审继续使用同ID/同IPA与官方--no-latest，在独立clean checkout执行。原失败本地目录、日志、回执均保留，原latest inode5133934未改变。
- 公开IPA完整下载摘要与受审制品一致：`dab0af9989cb1a41e4b28ef94225023a3d988b5b909211917545bba64f0bc916`。安装页、manifest、IPA、二维码均200。没有OTA/vendor update或TestFlight上传。

安装页：[小巴健康1.3.5(278)](https://health.executor.life/mobile-install/ios/20261012-admin-model-e580383da-278/install.html)。Ad-hoc仅已登记设备可安装；实际目标设备登记/安装、相机硬件、登录后原生业务UI及优化后真实拍照延时未验证。默认模拟器及未覆盖项风险按用户AGENTS选择保留；不得宣称Apple真机测试豁免。完成范围为实现、受审发布与上述验证，真实用户验收仍待使用反馈。
