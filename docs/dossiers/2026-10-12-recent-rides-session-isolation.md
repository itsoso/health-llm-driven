# 两段骑行查询与账户切换回归修复

状态：G3 验证中，尚未发布。Primary controller：health-harness-orchestrator；overlay：safety-gate。真实模型评测按用户要求取消。

## G1 准入

PASS：修复已有运动读取与登录会话隔离。截图原话为“分析青山湖骑行刚才的两段骑行。”；既有“分析刚才的运动”语法未覆盖类型与数量，导致未绑定当日范围。对象仍为已保存的 ExecutionEvent，无新对象、写权限或医疗裁决。Mobile 提问，Backend 绑定认证用户与本地当日窗口，数据库是事实源。

## G2 实现边界

- 全句语法绑定运动类型、有限数量与用户提供的地点描述。地点不证明实际 GPS，不按地点猜测记录名称。仅返回当前账号当天同类型已保存的候选记录；数量不符时披露不足或歧义，不能把任意记录合成所述两段，不自动同步设备。
- 否定、转述、他人、额外日期或操作无法取得个人读取权限。模型不得新增 owner、类型、limit 或扩大日期；单查与批查同边界。
- 完成状态验证实际 reader 的类型和数量元数据；回复保存包含确定性的数量说明。缺失指标维持未知，不作恢复等级、诊断或量化训练建议。
- 账户隔离审计复现六项失败：旧 keychain 覆盖新登录、退出后恢复旧凭证、普通请求异步等待后仍发送旧凭证，以及旧会话成功响应跨账户返回（含退出再登录相同 token）。以独立会话 generation 验证，保留当前会话 401 与 AI consent 边界。
- 停用全局明文 React Query 持久化，启动仅删除原 derived cache key，保留草稿与业务记录。同一会话内保留一分钟 staleTime / 一日 gcTime 内存缓存；会话切换同步清空缓存及已挂载 observer，取消在途查询，旧响应无法重新填充新账号缓存。冷启动需重新读取，暂不宣称具备加密离线健康缓存。

## G3 证据

初始 PostgreSQL 5 FAIL / 50 PASS；reader 新增测试进一步 9 FAIL / 50 PASS。第一轮完整链路发现四个已查询但保存回复未带数量的失败，保留失败并修复。邻近 PostgreSQL 测试第一轮 634 PASS。Mobile API 初始 6 FAIL / 29 PASS，修复后 35 PASS；实际 Axios 排队窗口额外回归待验证。所有数据库测试为独立临时 PostgreSQL、合成用户数据，无线上个人数据读取或同步。

最终 scoped PostgreSQL 639 PASS；覆盖截图原话普通/批量真实 dispatch 与保存回复、候选缺失、其他用户/日期/类型、元数据伪造与布尔数量拒绝。实际 Axios 排队新增四项 RED 后修复；caller 提供旧 Authorization 在退出后仍发送的额外 RED 已修复。API / 实际 Axios / 缓存 47 PASS 且正常退出、无 open handles；TypeScript PASS；System Map PASS。离线模型不变量 12、health_agent_core 50、trajectory contract 12 与 golden 9 全部 PASS，实际模型调用为零。

首次全 Mobile 347 suites 中 346 PASS，新增旧 header 测试 1 FAIL；其修复后的全量运行待完成，不以局部绿色替代该失败。未对拍照或线上响应速度作无基线的性能提升声明。

## G4–G6

待固定提交独立安全审查、项目 CI-mode、精确 main CI 和部署回执。未发布本次改动；前次 279 安装包不作为本次修复证据。实际 Garmin 数据同步、真实设备与真实模型表现未验证。

### f117 独立 G4 NO-GO 与修复

两项独立合成 RED：冷启动绕过持久 logout tombstone，残留钥匙串凭证仍可发送；骑行背景/例句中的公开知识请求被误拦。未 push / deploy。对应本机 f117 CI-mode 因候选被否决于 508.95 秒终止，exit -15，不能作为通过证据。

修复复用 auth.ts 的串行存储队列与持久退出屏障，API 仅读已存凭证、不安装 session 或写回共享存储；业务请求屏障读取失败关闭，显式新登录可无残留凭证进行。全句 recent 身份失配保留严格拒绝；未授权近期引用只拦个人工具，公开知识/城市环境仍走其原有权限。退出屏障新增真实 Axios 初始 2 FAIL / 7 PASS，修后 API/实际传输/auth 112 PASS；公开知识回归初始 1 FAIL / 63 PASS，修复后完整 PostgreSQL 待复验。f117 全 Mobile 347 suites / 3542 PASS、1 SKIP 已通过，但不代替修复候选的新全量验证与全新 G4。

### 81b8 G4 GO 与取消查询计时器修复

全新独立 reviewer 对固定 81b8 完整 diff 裁定应用 GO 与 ops 静态 GO；独立 PostgreSQL 640 PASS，TypeScript exit 0。其初次 archive 缺 ignored Pi 依赖导致 9 FAIL，补齐仅本机既有依赖后重跑通过，两轮均保留，未以依赖故障冒充代码通过。父全 Mobile 347 suites / 3546 PASS、1 SKIP，TypeScript PASS。

纠正此前“专项正常退出”：API/auth/cache 组合断言通过但实际进程仍存活，不能宣称无 open handles。定位 React Query 在取消 fetch 的 finally 中重新给已移除 query 安排一日 GC 计时器，额外真实 RED 1 FAIL / 6 PASS。退休 query 的 gcTime 归零，不改变新会话默认缓存生命周期；修后 52 项实际 Axios/API/cache 测试与 TypeScript 均真实正常退出 0。调试只发现短期零毫秒退休 GC，不再有一日遗留计时器。81b8 本机 CI-mode 因候选含这项后续修复于 332.95 秒终止、exit -15，保留但不接受。

后续提交需固定新 SHA 重审这项缓存生命周期补丁和四个发布 wrapper，重跑完整 Mobile/CI-mode/精确远端 CI；不得把 81b8 GO 或旧包结果冒充最终发布证据。
