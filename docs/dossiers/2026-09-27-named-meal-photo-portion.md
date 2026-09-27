# 指定餐别的照片份量记录修复

| 字段 | 值 |
| --- | --- |
| 状态 | release-blocked-before-live-mutation |
| Controller | health-harness-orchestrator · incident |
| Overlay | safety-gate |

Run: `docs/_generated/harness-runs/86ecfc26d33b.jsonl`。外部调试/TDD/verification 技能源未安装；遵循仓库先复现再修复及新鲜验证规则，不启用 superpowers。

## 范围与复现

附餐食/订单图的“记录晚餐 吃了一半”落入未保存兜底。只修已存在的饮食照片捕获语法，不改变权限、数据库 schema 或客户端协议。不部署、不改生产个人数据，保留高德及其他工作树改动。

源码与合成回归证明两个缺口：整餐比例只接受“这餐”等指代，不接受显式餐别的新建命令；订单实际摄入白名单只接受不带比例的短命令。前者将合法表达标成 ambiguous_fraction，后者即使比例解析正确仍只进入确认。截图没有线上调用链，因此不宣称排除了当次识别/provider 的其他故障。

## 修复边界

- 为当前餐次显式新建命令增加完整句式匹配，仅在附图比例解析中启用，不扩大通用历史修正语法。
- 已校验整餐比例且意图为 diet/create 才满足订单实际摄入条件；菜品缺数量、低置信度仍返回确认卡。
- 明确餐别优先于当前时钟的默认餐别；营养五项使用同一比例，保留幂等回执和照片关联。
- 取消、他人、计划、历史日期、疑问、多个比例、单菜比例继续禁止自动写入。

## 验证

- RED：新增命名餐别解析与捕获测试 11 failed / 56 passed，失败为比例未解析或记录不存在。
- 首轮修复整文件 134 passed；完整流/负向补测后相关组合 166 passed / 1 PostgreSQL-only skipped。
- 离线 LLM gate：invariants 12/12、core 50/50、trajectory 12/12、golden 9/9 通过。
- live-change gate 正确阻断；本机 live LLM 0/5，原因是默认 provider 未配置 / fallback recipient 未披露。未设置通过标志，未绕过同意/披露检查；合成 in-memory 测试的 usage 表缺失警告不作为审计通过。
- 最终合并复跑照片/聚餐服务、旧餐修正/日期/查询回归：SQLite **583 passed / 2 PostgreSQL-only skipped**。
- PostgreSQL 独立临时库：最终指定餐别比例、完整聊天回执/确认、禁止写入负例 **55 passed / 0 skipped**。只运行合成数据，未连接生产库。
- System Map、治理检查、tracked secret scan、`git diff --check` PASS；无生成结构变化，不新增依赖。

复跑：在 backend 下使用 `CI=1 DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai venv/bin/python -m pytest`，参数 `-o addopts='-q --strict-markers --tb=short --show-capture=no'`。文件组：

1. `tests/test_agent_executor_food_vision.py tests/test_diet_spoken_fraction_correction.py tests/test_agent_diet_correction_terminal.py`
2. `tests/test_contextual_meal_photo_service.py tests/test_contextual_meal_photo_policy.py tests/test_diet_shared_portion.py tests/test_diet_photo_correction.py`
3. `tests/test_latest_meal_correction.py tests/test_health_manage_date_normalize.py tests/test_query_reliability_executor.py`

PG 使用同一 food-vision 文件，选择 `named_meal_photo_fraction or half_order_stream or unsafe_photo_fraction`，独立 TEST_DATABASE_URL 必须带 test 库名（fixture 会建删测试表）。

## 安全预审

首次工作树预审发现 P2：两种新增解析语法被现有意图层判为 update，普通照片会误按时钟默认餐别保存。已在新增 named-capture 分支要求同样满足 diet/create 权限；冲突表达进入既有 no-write 护栏，不扩大纯文字修正权限。补充普通照片/订单四个捕获负例以及 parser/直接写入负例。

独立复审无预提交阻断；独立全 food-vision **151 passed**，另核对 11 个附图边界和 3 个纯文字非授权例。这是工作树预审，不替代正式 G4。

## 发布边界

尚未提交、push 或部署。正式 G4 需要固定候选提交后的独立审查；G5 需要 live LLM 和 exact-main CI 通过。本轮工作树预审不能替代发布 Gate。无需为这项后端修复单独 OTA。

## 2026-09-27 发布续接

用户明确要求“部署和发布ota”。按 backend-deploy + safety-gate 固定本修复候选；仅提交本 dossier、executor 与对应测试。高德 GPS/权限文案及其他工作树改动保留不发布。先完成固定提交正式 G4、同生产模型的合成 live gate、CI-mode 集成与精确 main CI，再部署。OTA 单独核对 runtime 与实际客户端变更，不用 OTA 冒充原生定位用途更新。

### 发布执行证据与阻断

- 候选 `ff3e6d331e7fbcb8b8a532b29749228a84928b07` 已提交并推送 main；精确 [CI 36311452253](https://github.com/itsoso/health-llm-driven/actions/runs/36311452253) conclusion=success，28 jobs 完成、无失败。
- 固定提交独立 G4 GO；独立测试 185 passed / 1 PostgreSQL-only skipped。干净发布目录 CI-mode agent-executor-food / d-diet 分片分别 151 passed 与 406 passed / 3 PostgreSQL-only skipped。
- 同生产模型配置仅内存加载，合成 in-memory 数据库 live gate 5/5、均分 0.92；invariants 12/12、core 50/50、trajectory 12/12、golden 9/9。未写生产用户数据。
- 客户端 mobile/shared runtime tree 与已发布 OTA 来源 `c0eb135eb87c4b90c00117b8c53e0875c1d05078` 相同；遵循 mobile-ota 禁止空更新规则，不发布内容相同的 OTA。
- 首次 deploy.sh 在 bundle 上传前发现独立发布目录缺少 `refs/reva-production`，当次 lease 自动释放、线上未变；核验真实生产 SHA 后补齐仅本地 Git 引用，再运行完整入口。
- 第二次在 Laya preparation 失败：`invalid Laya source metadata`。只读取证确认本次 `/tmp/health-app-deploy-44912-1790504178.bundle` 为 root:root、0644、单链接；受审准备脚本要求 0600。lock、stage、Laya base/sources 元数据符合要求。未现场 chmod、删锁或再次重跑。
- 保留 lease `/run/lock/health-app-release`，stage `/tmp/health-app-backup-preflight-44912-1790504178`；live env 未改变，未 checkout/停服。生产仍为 `bdf5fe616a4461c568f16fe5941a707c4cc287ea`，Git clean，backend/socket/worker/beat 均 active，公开 health 的 API/database/redis/celery 均 healthy/connected。
- 数据库备份按治理默认关闭；回滚 schema probe 通过。配置备份与候选封存已完成，不等于业务部署成功。
- G5 BLOCK：需修复 bundle 权限准备并经受控失败现场处置/发布流程后继续；当前修复尚未上线。本节为本地交接证据，未再次推送或变更发布候选。

### 发布权限修复续接

用户明确“继续”，授权修复发布脚本并受控处理原失败现场。实际根因是 `git bundle create` 替换 mktemp inode、使用调用者 umask，因此源文件在常见 022 下成为 0644。仅该创建步骤使用子 shell `umask 077`，不改调用者设置、不放宽远端 0600 检查、不修改旧 bundle。

- 新增真实 Git bundle + transport stub 回归：022/000 两种调用者 umask，修复前均失败；修复后验证源文件 regular/单链接/0600、bundle prerequisite/HEAD 正确、调用者 umask 不变。
- 补充旧 COMMITTED terminal + 新 publisher SHA + 相同封存 stage/env 的接管测试，证明 env 不上传、stage 文件与 manifest 字节/inode 不变；与错误 token/label/active SHA 等负例共 8 passed。
- 独立只读取证：原 14 个 staged 代码制品与候选源一致，live env 等于 sealed rollback/candidate；没有本次 journal/preparing，失败候选 Laya source 不存在。现有 deploy.sh 接管模式适用；trusted-launcher 专用 `--retire-unchanged` 不适用于本地直接发布，不伪造其回执。
- 新候选须先固定提交独立 G4、精确 main CI；之后私下读取原 token，以 `REVA_RELEASE_LOCK_ADOPT=1` 从干净候选执行唯一部署入口。发现现场漂移或 active journal 则停止，不清锁、不覆盖原 stage。

### 停止超时事故续接

权限修复 `1d310cdedf3ef58915bf6d4d5229e05a9d8cbe2a` 独立 G4 GO（28 项独立测试），干净候选 CI-mode 329 passed，精确 CI 36313310750 success。按原 token/stage 接管，bundle 与 Laya 准备成功。随后去激活停止 backend 超过 systemd 45 秒时限，systemd SIGKILL 后留下 `ActiveState=failed/Result=timeout`；原脚本仅接受 inactive，报 `DEACTIVATION_CONTAINMENT_FAILED`。

只读取证：production 仍 bdf5fe616、env 仍等于原 rollback/candidate、只有旧 COMMITTED terminal、没有新 journal；backend MainPID/ControlPID 均 0，ControlGroup 空且对应 cgroup 不存在，socket/worker/beat inactive，公网 health 502。已向用户明确报告暂时不可用。原 lease/stage 保留，不手工启动服务、改标签或执行无 journal 的整体 rollback。

最小续修仅在去激活锁内对已停止的确切服务执行 `reset-failed`：限定 failed/failed + timeout + MainPID/ControlPID=0 + ControlGroup 空 + cgroup 路径及链接均不存在，任一读取失败、残留进程、其他失败类型均 BLOCK；随后重新证明 inactive。仅继续原 `deploy:backend` 接管入口，不冒用 trusted-launcher 专用恢复链。新鲜 RED 为真实 stop-helper 场景 2 failed / 8 passed；修复后的定向测试还覆盖探针输出看似正确但退出失败的拒绝行为。
