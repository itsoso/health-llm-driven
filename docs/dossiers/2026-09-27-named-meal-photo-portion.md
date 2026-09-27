# 指定餐别的照片份量记录修复

| 字段 | 值 |
| --- | --- |
| 状态 | locally-verified-awaiting-release-gates |
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
