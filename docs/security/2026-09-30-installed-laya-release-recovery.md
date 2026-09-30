# 已安装 Laya 复用校验失败的发布收尾

2026-09-30 现场：e13cd67e953c09e38a049be4d8e07ae0686f0695 的 Trusted release
36648070016 在 checkout 前返回 LAYA_BLOCKED:TimeoutError。原 d55 后端、worker、beat
仍活动且零重启，ETH 三个进程 PID 与此前一致。原失败回执、sealed stage、租约完整保留。
Laya 原安装已存在，因此原未安装收尾模式不适用，不能删锁或重放部署。

本次新增独立的已安装复用 profile，写集沿用现有原证据归档、精确撤权和租约
同 inode 归档，不修改 Laya、业务配置、原失败回执或生产成功状态。源码、模型、
依赖、配置、旧成功回执、历史安装来源、实际服务身份均须一致；详见部署规范。

现场独立只读验证：未认证请求返回 401；相同 choice/score/noul 合成推理返回 200，
耗时 0.73 秒。只能确认当前探针恢复，单次 TimeoutError 的历史资源竞争原因未知。
新发布仍必须完整执行原探针，不放宽超时、不跳过 Laya 验证。

本文件编写时收尾和后续发布尚未执行。验证和独立 G4 证据随后更新。

## 当日依赖审计刷新

b79 CI 36660647091 的在线审计阻断 PyJWT 2.13.0 及 Mobile 构建依赖的已知漏洞。
最小升级为 PyJWT 2.14.0（重新生成 hash lock）、brace-expansion 的同主版本
1.1.21 / 2.1.7 / 5.0.12 与 joi 17.13.8。未添加审计忽略项，未改变原生模块版本。
依据：[PyJWT 公告](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-9v7f-9g4p-ffgj)、
[brace-expansion 公告](https://github.com/advisories/GHSA-qhr7-859c-m2p7)、
[joi 公告](https://github.com/advisories/GHSA-6h2x-m376-mqjq)。

同类 parser 补丁同步覆盖隔离发布工具的锁文件，并更新既有精确版本契约。
保留各消费者原主版本，下载地址和 SRI 绑定官方 npm registry。
