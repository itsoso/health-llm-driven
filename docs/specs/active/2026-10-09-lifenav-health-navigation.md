# LifeNav 健康导航第一阶段

> Status: implemented-local; external-validation-pending · Owner: Health backend · Updated: 2026-10-09
> 依据：[整合计划](../../plans/2026-10-09-lifenav-reva-integration-plan.md)

## 决策与准入

在 Health 原有写入流程物化日行动身份和状态；提供无业务副作用的滚动七天投影、本人详情与确认。LifeNav 仅通过已核验接收方的独立 grant 读取泛化投影。Health 是健康事实、计划与执行唯一真源。

RequirementAdmission：product_change；HealthAgendaItem/LeverageAction/ExecutionEvent；Mobile 与专用外部展示；privacy_sensitive；autonomy=none；不作医学因果裁决；验证窗口为完整七天；每日新增必填字段为零。用户本轮授权实施全计划，真实外发仍须接收方身份与数据流核验通过。

## 对象、源写入与统计

新增 user/source/local_date/action_key 唯一 occurrence。UUID 引用不包含健康内容。相同发生次序的内容、安全或执行状态变更增加 revision；同名跨天不合并。源计划再生成后消失的未终态项记 withdrawn，已完成/跳过终态保留；后续 defer 不把完成事实复活。旧反馈与 event 两条原写路径在同一事务更新索引；外部 GET 不回填、生成计划或触发 LLM。

原始写入计划的 AdviceGuard 明确 allowed 才产生新投影中的 allowed；失败或不明 fail closed。普通行动 key 白名单仅映射固定泛化文案，动态/医疗行动保留 Health 内部详情，不外传正文、药名、病名、数值。固定/未知时点 view_only。安全快照最多五分钟，失效展示 unknown；本人确认前重新运行现有计划安全检查并比较冻结 revision。

七天使用本人 IANA 时区，含当日。latest authoritative occurrence 状态归并后计数，unknown 单列；无稳定分母，不返回 planned_occurrences/completion_rate 或因果结论。尚未生成返回 not_generated，不冒充空计划。时间窗、源数据版本和授权视图进入确定性 hash；generated_at 不影响内容版本。

## 接口与跨端契约

GET /health-navigation/summary：v1 DTO，actions 与 review，来源/时区/缺失明确。
POST /health-navigation/refresh：本人显式刷新，通过原计划写入方生成和安全校验。
GET /health-navigation/actions/{ref}：本人认证、owner 检查，失效/他人引用 404。
POST /health-navigation/actions/{ref}/events：本人确认，expected_revision 与 UUID operation_id；事务锁定；同键同内容返回原结果，异内容或源版本变化409；不接受集成凭据、API Key或家庭代理。客户端不乐观标完成，超时使用原 operation_id 重试。
LifeNav grant/API 的字段和协议见整合计划6/7章；接收方配置默认空、外部开关默认关闭。grant只读独立 audience，固定回调与PKCE，一次性code，服务端凭据；默认七天授权，无外部写入。

Mobile 复用我的进展的 navigation=week 模式，替换该模式中旧完成比率和旧复盘查询；来源详情登录恢复后重新取数。原模式继续。Watch/Mac不增加平行页面。HTTPS universal link 未实现时明确记录，不修改原生配置冒充OTA。

## 安全与验收

不得导出原始 Twin、自由文本、医学指标、药剂名、家庭代理数据或诊断。首期确定性投影，不调用LLM、不进入LifeNav AI/备份。本人客户端清理内存缓存、账号切换与过期清除；凭据只存在已核验接收端服务端。

必须测试：只读数据库事务GET；跨用户/授权到期/撤销/旧路由拒绝；重复事件和跨天key；状态消失保留终态；不明安全和旧观测不显示许可；确认幂等/版本冲突/撤权竞态；界面不显示伪完成率；源写失败不伪装成功。SQLite单测与PostgreSQL语义分别验证，新迁移成对且可幂等回放。

## 发布、回退和边界

向后兼容新增表；原接口继续。撤掉新入口与外部开关即可回原流程；保留审计及执行事实，应用回退不删除新增表。真实外接在W0未完成时保持关闭。W6完整七天现场验证不能由即时单测替代；W7为试点价值验证后的独立扩展，默认不启动健康目标/计划自动写入。

## 验证计划

backend/venv/bin/python -m pytest 新测试及daily-plan/复盘/权限回归；隔离PostgreSQL同批验证；Mobile类型与相关服务/页面测试；System Map生成和中央检查；独立安全review；发布与现场验收分别记录Dossier。

## 变更

2026-10-09：第一阶段Health端实现，独立代码安全GO；真实接收端、跨App回跳、七天试点与发布仍待各自Gate。
