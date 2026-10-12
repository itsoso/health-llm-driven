# 两段骑行查询与账户切换回归修复

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3：补修骑行照片误入饮食链路；新候选尚未部署 |

Primary controller：health-harness-orchestrator；overlay：safety-gate。真实模型评测按用户要求取消。

## G1 准入

裁决：PASS。修复已有运动读取与登录会话隔离。截图原话为“分析青山湖骑行刚才的两段骑行。”；既有“分析刚才的运动”语法未覆盖类型与数量，导致未绑定当日范围。对象仍为已保存的 ExecutionEvent，无新对象、写权限或医疗裁决。Mobile 提问，Backend 绑定认证用户与本地当日窗口，数据库是事实源。

## G2 实现边界

裁决：PASS。

- 全句语法绑定运动类型、有限数量与用户提供的地点描述。地点不证明实际 GPS，不按地点猜测记录名称。仅返回当前账号当天同类型已保存的候选记录；数量不符时披露不足或歧义，不能把任意记录合成所述两段，不自动同步设备。
- 否定、转述、他人、额外日期或操作无法取得个人读取权限。模型不得新增 owner、类型、limit 或扩大日期；单查与批查同边界。
- 完成状态验证实际 reader 的类型和数量元数据；回复保存包含确定性的数量说明。缺失指标维持未知，不作恢复等级、诊断或量化训练建议。
- 账户隔离审计复现六项失败：旧 keychain 覆盖新登录、退出后恢复旧凭证、普通请求异步等待后仍发送旧凭证，以及旧会话成功响应跨账户返回（含退出再登录相同 token）。以独立会话 generation 验证，保留当前会话 401 与 AI consent 边界。
- 停用全局明文 React Query 持久化，启动仅删除原 derived cache key，保留草稿与业务记录。同一会话内保留一分钟 staleTime / 一日 gcTime 内存缓存；会话切换同步清空缓存及已挂载 observer，取消在途查询，旧响应无法重新填充新账号缓存。冷启动需重新读取，暂不宣称具备加密离线健康缓存。

## G3 证据

上一已发布批次为绿。当前照片分流修复的完整回归待完成。上一批最终运行时代码 PostgreSQL 640 PASS；完整 Mobile 347 suites / 3547 PASS、1 SKIP；TypeScript、System Map 与离线合成门通过。实际 Axios/API/cache 52 PASS 正常退出。固定 82fd8d086f4a1e9d9383950a1e49b9e69c488fae 的本机项目 CI-mode 3595 PASS、22 SKIP、84 subtests PASS、exit 0；远端完整恢复 CI 38206912576 与文档 push CI 38206911542 均成功。

初始 PostgreSQL 5 FAIL / 50 PASS；reader 新增测试进一步 9 FAIL / 50 PASS。第一轮完整链路发现四个已查询但保存回复未带数量的失败，保留失败并修复。邻近 PostgreSQL 测试第一轮 634 PASS。Mobile API 初始 6 FAIL / 29 PASS，修复后 35 PASS；实际 Axios 排队窗口额外回归待验证。所有数据库测试为独立临时 PostgreSQL、合成用户数据，无线上个人数据读取或同步。

最终 scoped PostgreSQL 639 PASS；覆盖截图原话普通/批量真实 dispatch 与保存回复、候选缺失、其他用户/日期/类型、元数据伪造与布尔数量拒绝。实际 Axios 排队新增四项 RED 后修复；caller 提供旧 Authorization 在退出后仍发送的额外 RED 已修复。API / 实际 Axios / 缓存 47 PASS 且正常退出、无 open handles；TypeScript PASS；System Map PASS。离线模型不变量 12、health_agent_core 50、trajectory contract 12 与 golden 9 全部 PASS，实际模型调用为零。

首次全 Mobile 347 suites 中 346 PASS，新增旧 header 测试 1 FAIL；其修复后的全量运行待完成，不以局部绿色替代该失败。未对拍照或线上响应速度作无基线的性能提升声明。

## G4 安全审查

上一已发布批次为 GO；当前照片分流候选待独立审查。固定运行时候选 f6caece330dcfc54f50cfc3bcc278e0a6be02765 独立应用 GO、ops 静态 GO，额外缓存回归 8 PASS，正常退出。独立 reviewer 对最终 82fd8d0 的文档后继与四个精确包装器重新绑定 GO；运行时 tree 与 f6ca 相同。实际 280 IPA 的摘要、签名、原始回执、profile、双 iPad orientation keys 和精确来源独立复核 GO。静态审查之外，官方发布流程实时准入均通过。

## G5 发布健康

当前照片分流修复尚未发布；下文是此前发布的 PASS 证据。精确 82fd8d0 可信后端发布 [38210061452](https://github.com/itsoso/health-llm-driven/actions/runs/38210061452) 成功；生产持久回执为 SUCCEEDED，HEAD 精确匹配且工作树干净，四个服务 active，公开健康接口 HTTP 200 / healthy，发布租约已释放。五个后端实现文件逐项摘要与来源匹配。旧前端制品 tree 未变化并经 canonical 活体绑定校验，旧 backend / OTA 历史回执与锁保留。

1.3.5（280）按官方 local-qr 流程构建并一次性发布。公开 install.html / manifest.plist / qr.png / app.ipa 均 HTTP 200，整包下载摘要与独立验收 IPA 一致；manifest 绑定 build 280 与实际不可变目录，旧 latest 保留。安装页：[280 iPhone / iPad 安装包](https://health.executor.life/mobile-install/ios/20261012-rides-session-82fd8d086-280/install.html)。包只允许 provisioning profile 中已登记的设备，不代表所有 iPad 已可安装。

当前精确源码经官方 OTA validate_source 检查，冻结 native baseline 不兼容；未调用 vendor 或消费 OTA claim，使用新原生包交付，未发 TestFlight。用户明确取消真实模型评测，actual model calls 为零且 confirmed=false。发布后已清除仅绑定本 SHA 的临时仓库豁免变量，读取确认该变量不存在。

历史失败保留：f6ca 完整 CI 38206017342 的 Dossier 一致性检查失败，原因是此前缺可解析状态表和 G1 裁决；82fd 只修正文档格式并主动补跑完整 CI 38206912576。没有取消、重跑原失败或使用 docs-only 绿色代替运行时门禁。

## G6 上线验收

生产部署源码的合成范围检查通过：截图原话允许 authenticated owner 的今天 cycling 查询，expected_count=2；类型/数量扩大、他人、否定及隐式同步拒绝，数据库读取与实际模型调用均为零。该探针只证明线上代码路径，不证明真实账号已保存两段骑行或青山湖 GPS 身份。

同 SHA 的 Release 模拟器 build 280 实际安装 metadata 已核对；三次启动、横竖屏切换和密码输入框可操作检查通过。六个 XCUIScreen 附件保留，三次 landscape frame 为 1376×1032；实际一张横屏和一张竖屏截图已查看。PNG 存储尺寸带旋转信息，不用原始像素方向代替 UI frame 验收。真机相机、真实账号骑行记录、Garmin 实际同步和真实模型表现未验证，故 G6 不记为真实账号验收通过，状态仍为 shipping。

完整交付证据：[发布摘要](../reviews/2026-10-12-recent-rides-session-release-summary.json)。后端回退参考为 04d2724de89a4e90da42a5b2e111c87a878365f7，旧 279 安装包保留；任何回退仍须官方准入，不能重放本次发布。

### 首轮独立审查 NO-GO 与修复

两项独立合成 RED：冷启动绕过持久 logout tombstone，残留钥匙串凭证仍可发送；骑行背景/例句中的公开知识请求被误拦。未 push / deploy。对应本机 f117 CI-mode 因候选被否决于 508.95 秒终止，exit -15，不能作为通过证据。

修复复用 auth.ts 的串行存储队列与持久退出屏障，API 仅读已存凭证、不安装 session 或写回共享存储；业务请求屏障读取失败关闭，显式新登录可无残留凭证进行。全句 recent 身份失配保留严格拒绝；未授权近期引用只拦个人工具，公开知识/城市环境仍走其原有权限。退出屏障新增真实 Axios 初始 2 FAIL / 7 PASS，修后 API/实际传输/auth 112 PASS；公开知识回归初始 1 FAIL / 63 PASS，修复后完整 PostgreSQL 待复验。f117 全 Mobile 347 suites / 3542 PASS、1 SKIP 已通过，但不代替修复候选的新全量验证与全新 G4。

### 81b8 独立审查通过与取消查询计时器修复

全新独立 reviewer 对固定 81b8 完整 diff 裁定应用 GO 与 ops 静态 GO；独立 PostgreSQL 640 PASS，TypeScript exit 0。其初次 archive 缺 ignored Pi 依赖导致 9 FAIL，补齐仅本机既有依赖后重跑通过，两轮均保留，未以依赖故障冒充代码通过。父全 Mobile 347 suites / 3546 PASS、1 SKIP，TypeScript PASS。

纠正此前“专项正常退出”：API/auth/cache 组合断言通过但实际进程仍存活，不能宣称无 open handles。定位 React Query 在取消 fetch 的 finally 中重新给已移除 query 安排一日 GC 计时器，额外真实 RED 1 FAIL / 6 PASS。退休 query 的 gcTime 归零，不改变新会话默认缓存生命周期；修后 52 项实际 Axios/API/cache 测试与 TypeScript 均真实正常退出 0。调试只发现短期零毫秒退休 GC，不再有一日遗留计时器。81b8 本机 CI-mode 因候选含这项后续修复于 332.95 秒终止、exit -15，保留但不接受。

后续提交需固定新 SHA 重审这项缓存生命周期补丁和四个发布 wrapper，重跑完整 Mobile/CI-mode/精确远端 CI；不得把 81b8 GO 或旧包结果冒充最终发布证据。

### 新增截图：骑行照片误入饮食链路

用户原话“骑行就不要记录为用餐了”，截图为风景照片加“记录青山湖骑行”，进度却显示识别餐食。此次继续修复同一运动记录闭环，退回实现与验证；旧 82fd / 280 发布保持有效，不作为新候选证据。

复现根因：通用图像预处理无条件先调用食物识别；contextual capture 将任意 write 意图升级为 EXPLICIT_CAPTURE。明确运动 caption 可被食物识别误判及旧相机餐食上下文转为饮食候选。新增运动附件排除只撤销饮食权限，不授予运动写入；保留图片原始通用附件，运动类型、时长仍走既有写入/澄清边界，不从风景照片猜距离、GPS 或耗时。常规餐食与完整肯定的运动后摄入/餐次指令保留既有饮食管线；复杂混合、否定或转述不据此自动记餐。

四项 PostgreSQL RED 真实复现：普通和旧餐食 metadata 两种实际 stream 都调用 food recognition；直接 capture 可错误自动记餐；普通 vision 优先调用 food preprocessor。修后四项 PostgreSQL PASS，实际 stream 无 diet_photo 进度，旧餐食 instruction 被剥除，用户图片仍保存为通用附件，diet create/manage 均在 HTTP 前拒绝。全部合成照片/用户，无真实模型和线上个人数据读取。初始测试未设置专用 DB 的连接失败以及 SQLite 被 db fixture 拒绝，均为环境失败，不冒充 RED；后续使用独立临时 PostgreSQL 并正常关闭。完整邻近 PostgreSQL 回归、独立 G4 与新候选 CI/部署尚待完成。

### 运动照片首轮独立审查否决与收紧

76b0a462c 本地候选独立 NO-GO，未 push / deploy。三个新增真实 PostgreSQL RED：“记录青山湖骑行，不是食物”“记录青山湖骑行，没吃东西”“记录青山湖骑行，旁边的人在喝彩”均被 raw 食物词解除运动排除，并真实生成饮食及图片资产。独立证据 /tmp/reva-riding-safety-negative-pg.log 保留。

收紧例外为完整、肯定的运动后摄入/餐次语法，否定、转述、其他动作和多子句不解除排除；任意 write 不再一律成为 meal EXPLICIT_CAPTURE，需 diet domain。仅撤销饮食权限；补剂/医疗报告预处理入口仍走其原有规则。新候选等待新鲜复审。第一轮邻近 PostgreSQL 272 项断言通过但 runner 在临时 PG fast-stop 超时退出 1，不能当 runner 正常完成；该旧候选也被否决。第二次测试因旧测试端口尚释放中而在 startup 失败，未跑断言；另用全新独立端口重新验证，不复用前次 DB。

### 第二轮独立审查否决与闭合命令

a3cefe4f1 仍 NO-GO，未 push / deploy。独立 PostgreSQL 对抗 17 PASS / 3 FAIL：运动后吃了鸡蛋后追加是假设、仅为示例或（妈妈的），任意食物尾文本仍能通过例外并写餐食。新修订移除全部自由摄入尾文本例外，只认可有限运动后背景加完整餐次记录命令；复杂混合摄入仍作为通用附件处理，不自动入饮食。运动饮料为已有食品字面容器，不作为运动事件；这不授予额外写权限。

同步既有体重测试：记录体重71kg不得生成餐食确认草稿，旧期望一份diet draft已改为0。新增补剂预处理正向句改为既有分类器可识别的记录补剂，今天骑行；不把未支持的运动后记录这瓶补剂误记为通过。父 a3ce 邻近 PostgreSQL 1 FAIL / 276 PASS，保留失败不洗绿；对应本机 CI-mode 由于候选被否决仅终止本任务 pytest 子进程，待记录真实终态，不作为通过证据。全新固定候选仍需独立G4。
