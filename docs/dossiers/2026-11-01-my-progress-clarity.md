# 我的进度页面优化

| 字段 | 值 |
| --- | --- |
| 状态 | ota_blocked_unpublished_claim |
| 当前阶段 | G5 OTA 领取前失败待收口 / G6 未完成 |
| Controller | health-harness-orchestrator; safety-gate overlay |

## G1 准入

裁决: PASS

用户截图要求优化现有进度页，范围是执行回顾、指标观察和建议详情的信息层级、
空状态及错误比例。规格：docs/specs/2026-11-01-my-progress-clarity.md。
不新增健康写入或自主建议，不将指标相关变化宣称为 AI 导致的改善。

## 范围与基线

已授权的隔离 worktree 续用，基线 bd4a4f4f795f6ae25e6825a7adf35bcff0efd738。
共享 main 的其他未提交改动保持原样。源码确认 graded 与 completed 并非子集，
原页面有 0/0、2/0、零行动 0% 和不恰当因果文案；当前任务仅调整展示与读取边界。

## 验证及发布

- UI RED: 原页面 8 个行为用例失败；随后补前后记录完整性及专业复核提示 RED。
- Session RED: 原服务 10 个隔离用例失败，另补两个旧 refresh 回调失败用例。
- 新鲜定向 GREEN: 页面、结果颜色、session hook/service、既有 review 共 5 suites / 45 tests。
- TypeScript、设计 token、System Map / 导航与文档漂移检查通过；新增页面测试引起地图路由计数由生成器同步。
- CI=true 全量移动端：主套件 382 suites / 3905 passed / 1 existing skip；隔离输入框 84、聊天 88、认证 34、GPS 7，合计 4118 passed。最终 useMemo 引用整理追加 hook 10 tests 通过。
- 本地 Simulator Release 构建成功；打包发生于最终 useMemo 整理前，不作为最终候选点击验收。Mac 锁屏阻挡实际点击，设备接收 OTA 也未验证。
- 独立 G4 GO 绑定累计候选 `9a530fd2778ad8b8134a16db2941a4365d9d9836`，独立回归 4 suites / 41 tests；最终 tsc、定向 ESLint、秘密扫描、diff check 通过。
- [精确主干 CI 41277052617](https://github.com/itsoso/health-llm-driven/actions/runs/41277052617) 全部 32 jobs 成功。
- [发布 validate 41277698865](https://github.com/itsoso/health-llm-driven/actions/runs/41277698865) 成功。
- [后端发布 41278851235](https://github.com/itsoso/health-llm-driven/actions/runs/41278851235) 成功；服务器 `/var/lib/reva-release/9a530fd2778ad8b8134a16db2941a4365d9d9836/completed.json` 为 SUCCEEDED，生产 SHA 匹配，health-backend / celery-worker / celery-beat 均 active。
- 部署健康评分 60/60；公开 `/api/v1/health` 返回 200，匿名进度与 review 读取均返回 401。
- [OTA validate 41279223434](https://github.com/itsoso/health-llm-driven/actions/runs/41279223434) 成功。
- [OTA publish 41279412983](https://github.com/itsoso/health-llm-driven/actions/runs/41279412983) 失败，官方诊断为 `claim-ota` / `command_failed`。当前原操作保留 `intent.json` 与 `lease.json`，没有 `claimed.json`、vendor receipt 或完成回执；业务 lease 尚未收口。后端成功不代表 OTA 已发布或设备已接收。

## 发布准备异常及收口

首次 canonical staging fetch 在 180 秒超时；原失败回执保留。只读发现对象已完整落盘，六文件库存、FETCH_HEAD 和 fsck 均验证通过。首个受限 checkout 续接因旧版本仅发布后端、没有 build.lock 而在任何远端 intent / checkout 前失败，记录继续保留。

独立审查后的精确无 build.lock 续接只持既有 launcher 锁，反复验证锁持续不存在、原对象及两组失败证据不变；未重新 fetch、清理、备份或重发部署。原 source 完成 checkout，独立本地/远端完成回执及干净 HEAD 验证通过。服务器审计路径为候选 bootstrap 下 `stage-continuation/`，completed SHA256 `00f30aac25de2f8b1251791f1c7859045ba96a5303a3617d8716b962254b75bc`。

同权限只读 App credential 首次刷新 `progress-read-credential-9a530fd2-v1` 成功，本地与远端回执相同；canonical 授权从 `bd4a4f4f795f6ae25e6825a7adf35bcff0efd738` 成功轮换到候选，随后只执行一次 backend 发布。所有原失败、审查及成功回执保留，未备份或恢复旧配置。


## OTA 领取前失败与待收口

固定 profile 绑定原候选 `9a530fd2778ad8b8134a16db2941a4365d9d9836`、run
`41279412983`、attempt `1`、job `124768075123`、artifact `13072503978`
（2565 bytes）。官方 ZIP、三份规范 JSON 及原候选四项控制流源码摘要均已核对；
`SOURCE_HASHES` 来自固定 `git show 9a530fd…:<file>`，不取当前工作区字节。
profile 只允许关闭此未发布失败，不生成 OTA 成功回执、不重发原 operation。
全部四个 lease 文件强制绑定 device、inode、内容摘要与 `ctime_ns`，历史 profile 边界保持。

- 本地 profile 提交：`44b1a3fb1406ad35b78360366c27fb4e2ea80a44`，尚未 push。
- RED：未支持新 profile 时 25 failed、35 setup errors，均因未知固定 profile；8 passed。
  GREEN：完整关闭器回归 396 passed、3 expected legacy-schema skips，diff check 通过。
- 独立 G4：reviewer `diet_detail_safety_review` 明确 GO，绑定上述 44b 提交；独立重复
  396 passed / 3 expected skips，并核对官方 metadata、ZIP 与控制流摘要。证据为评审消息，
  尚无单独持久报告文件。
- 原失败及 intent/lease 保持原状，尚未执行关闭，不能写“已收口”。
  必须由后续精确绿色 reviewed SHA，重新核验原租约、双锁、后端终态及健康后才可执行。
- 无 profiling 的 canonical 只读诊断成功：prepare 2.93 秒、本地完整校验 221.28 秒，
  `COMPATIBLE`、exit 0；保护文件与原 lease 身份摘要的两项 unchanged 均为 true。
  带 profiling 的校验耗时 550.64 秒，仅最后有效期检查失败；该插桩时间不能作正常基线。
  两次诊断都未复现原 publish run 的失败，直连 GitHub 元数据 TLS 超时也不作根因证据。
- 正常本地校验距旧 240 秒有效期仅余约 19 秒，原代码的 120 秒基线注释已过时。
  以此预算风险为依据，将固定 TTL 最小调整至 480 秒（约新正常基线两倍，低于
  server 600 秒 / publisher 900 秒），不改 CI 后起算、消费前后过期检查、单次消费及
  生产 revision/历史/租约/健康校验。这是余量修正，不是已确诊的原失败根因修复。
- TTL RED：313 秒及 480 秒的完整本地校验模拟在旧预算下失败（2 failed / 4 passed）；
  313 秒是测试压力场景，不是线上实测。GREEN：`scripts/test_testflight_only.py`
  全部 48 passed，包括 481 秒前后过期拒绝、失败后不可复用及既有生产漂移检查。
  追加 CI=true 发布关联八套件回归 1092 passed / 4 skipped / 7 duplicate-ZIP 负向测试 warnings。
  本次 TTL 修改需重新 G4 与精确主干 CI；44b 的 GO 不覆盖该新增修改。
  原失败 operation 仍未收口，不得重发原 SHA、清锁或伪造终态。


## 展示及数据边界

本期行动、身体变化与建议进展分区；不把零分母变成零分，不使用 graded/completed
漏斗。前后记录必须完整、有限且至少两次；涨跌中性显示并保留观察性边界。
评估说明默认折叠，专业复核提示保持可见。保留周期切换、建议详情及周导航。
双区块刷新，失败按区块展示安全重试，不暴露原始错误。按 owner/consent revision/
auth generation/window 隔离读取，旧响应及旧 refresh 回调不可进入新会话。
