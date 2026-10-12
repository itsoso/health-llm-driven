# Dossier: 日常安排误报与管理员模型入口

| 字段 | 值 |
|---|---|
| slug | daily-draft-admin-model |
| 日期 | 2026-10-12 |
| 当前阶段 | G4 固定候选审查 |
| 状态 | building |
| 负责 | root |

## G1/G2

裁决: PASS。用户截图“规划今天饮食运动和睡眠”反复出现通用查询失败，并要求优化性能、模型下拉只对管理员开放且不出现tokenplan。准入见 docs/specs/active/2026-10-12-daily-draft-admin-model.md。复用当前输入建议scope，闭合请求只允许通用知识；不新增个人读取或计划写入。管理员模型权限同时覆盖Mobile/Web、API、偏好provider、图片和工具门控consumer、per-request extra_context；当前数据库角色是授权真源。

## G3

实际截图原话先5 failed/7 passed，修改后Pi/panel均单轮完成、无个人工具、不误入睡前固定答复。个人依据、他人、取消、写入和未知尾句负向边界保留严格策略。权限RED首次fixture缺name/独立旧模块加载缺测试env，保留配置错误，不当行为证据；补齐fixture/env后旧API真实403约束失败。Mobile/Web成员缓存options和tokenplan RED均2例失败；实现后Mobile Picker/Header11例、Chat合计84例、Web5例通过，两端tsc通过。后端邻近232例230 passed/2 skipped；覆盖全部模型consumer的追加73例通过。PG第一次cluster错误使用ASCII编码，9个fixture错误；UTF8新集群19 passed、shutdown exit0，真实权限join与Pi/panel路径通过，旧错误日志保留。不得把本地单轮当成实际线上总延时。

## G4

工作树独立安全预审无阻断，补selftest在provider前拒绝及管理员降权后所有consumer测试；待固定候选独立GO。

## G5/G6

尚未部署本批修复。拍照路由等待修复a75另已部署，不能冒充此新批次。整合另一session已明确交接的菜单返回修复，见其dossier；保留无关benchmark实验。实际Mobile界面需候选模拟器/分发证据；当前OTA原生基线与iPad候选不兼容，不绕闸。

## CI 断点

360bf9f6a完整CI的docs-quality阻断：G1缺机器可识别的裁决前缀、菜单交接dossier缺状态/阶段与G1。补齐真实裁决与字段，不降低检查，不覆盖原运行。360的私有安装包不能作为通过CI的交付候选。
