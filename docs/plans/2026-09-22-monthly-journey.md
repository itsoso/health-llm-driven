# 这一路实施计划

> Status: draft; Updated: 2026-09-22
> PRD: docs/prd/2026-09-22-monthly-journey.md
> Contract: docs/specs/active/2026-09-22-monthly-journey.md

## 数据流与范围

复用原 diet/life_event/chat_photo 记录 -> JourneyPlace 注释 -> owner 月分页
-> 城市节点示意 -> 去敏分享模型 -> 本地长图；原始健康记录不重复写。
G1 用户已选完整版；G2 独立只读审查先于实现；没有新依赖和新模型调用。

## T1 Backend / DB

- 先写接口/隐私/约束失败测试，再最小实现 JourneyPlace、schema/service/api。
- 三源归属、私有图片白名单、版本并发；source/account 删除验证。
- 成对 managed SQL；严格城市加密；导出审计；失败显式，日志无载荷。
- 锁边界/唯一冲突、按 owner/date 索引与时区在 PostgreSQL 验证。

## T2 Mobile

- 独立 journey service/types、城市编辑组件、月度页面；聊天更多入口。
- 正常、错误、空态、分页、月份/账户切换；回调防迟到写入。
- 单次 foreground 定位由显式按钮触发；历史日期不取当前定位。
- 分享投影、选择照片与记录、有限等比长图、预览与 native share，清理临时文件。
- 先失败测试；同批 Jest + TypeScript，复用现有保护图片/分享工具。

## T3 Integration / Native

- 主代理同步 app.json 的两处用途说明，保持 Always 与后台开关关闭。
- API generated types 同步客户端；生成 System Map/mobile navigation 结构。
- iOS Simulator 路径与截图检查；硬件定位/第三方 App 交接列明未验证。
- 修复先前后台身份 Dossier 的格式，使全仓文档闸可解析；不修改其历史结论。

## G3/G4 与停止条件

T1/T2 可在互不重叠文件并行；共享 main，禁止切分支和覆盖其他修改。
完成后 CI-mode 增量合跑、PostgreSQL、native 配置、tsc/Jest、模拟器、
地图/文档/秘密扫描；固定本地提交后独立安全评审。
源隔离/删除/分享隐私/模拟器功能红项不得继续发布。不能缩测试洗绿。

## 发布路由（暂不执行）

后端 deploy -> 新安装包（默认 local QR，不擅自 TestFlight/EAS submit）。
用户要求全部修复后统一发布；当前仍有其他待决功能，保持未发布状态。
回滚保留新增表和数据，移除/禁用入口；没有回填历史定位或批量写入。
