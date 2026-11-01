# 本周血氧绘图授权与展示修复

| 字段 | 值 |
| --- | --- |
| 状态 | implementation_verified |
| 当前阶段 | G3 本地回归通过；G4 独立安全审查待完成 |
| 工作流 | quick_fix + safety-gate → backend-deploy + trusted OTA |
| 基线 | 23202c56a97014c6e42454562c1ed1e14e786d8d |

## 范围与根因

截图中的绘图请求被拒绝为未授权读取。使用合成请求与冻结时间复现：
“绘制本周血氧饱和度数据”命中 `health_query_not_requested`；换成查询动词后，
完整指标名仍命中 `longitudinal_read_scope_unresolved`。既有“查询本周血氧数据”通过。

- 只将完整的本人周范围血氧绘图请求投影为查询；绘制/画出不加入通用读取动词。
  原始文本边界在 scope 与 gateway 重验，防止下游删去附加条件后意外生成授权。
- 血氧领域完整消费“血氧饱和度”，仍保留未知筛选条件、第三人称、引述、假设、
  撤回、模型 owner/date/timezone 注入的阻断。
- 图表仅投影本轮成功执行、已绑定 owner 与精确日期的只读结果，不再查数据库，
  不使用旧图、不走默认半年窗口。模型滚动 days 提示被规范为用户本周的冻结日期。
- 现有 line_chart 契约展示日均血氧，缺失为 null，数值经统一展示格式化；
  结果窗口不符、越界/重复日期、非法数值、失败结果和不合格来源不生成图。
  无日均值不由采样或缺失值编造。保留采样与日汇总非睡眠连续监测的边界。
- Mobile 在缺失日期断线，孤立观测与单点仍可见。没有原生、API schema 或 DB 迁移变化。
- 复用已授权隔离 worktree，未修改共享 dirty main。

## G3 验证

- 授权 RED：原实现 2 failed / 1 passed，准确覆盖两种拒绝原因。
- 图表投影 RED：14 failed；Mobile 缺口/单点 RED：3 failed。
- 后端相关 CI-mode 合跑：3787 passed，SQLite 合成记录；真实 Pi 协议运行，
  仅模型输出替换为测试响应。覆盖 capability policy、共享语义、只读 scope、
  GenUI 表格/用药投影及图表防伪造回归。
- 新流式用例通过真实 gateway/dispatcher/reader：冻结周一至当前业务日，
  排除前周、未来日期与另一用户记录；客户端声明能力时只发一张图，无能力时不发。
- Mobile Node22：3 suites / 126 passed；TypeScript、ESLint、design tokens、
  System Map 与 diff check 通过。生成物已同步。
- 本机初始 Pi runtime 依赖缺失导致协议测试失败；按锁文件 npm ci 后重跑通过。
  不将缺依赖的失败解释为产品快速路由问题。
- SQLite 仅证明合成单元/协议行为；未改数据库查询语义，PostgreSQL 与完整 CI
  仍待目标 SHA 的线上 CI 验证。模拟器实际操作、发布与设备接收尚未核验。

## G4–G6

待固定提交独立安全审查、精确主干完整 CI、后端发布及 trusted OTA validate/publish。
所有生产、OTA 回执与线上验证须另行追加，不能由本地测试替代。


## 首轮 G4 NO-GO 与整改

独立 reviewer 拒绝 f786fffd5：将绘制/画出加入共享动词表后，化验/病史等旧消费者
存在取消、完成、是否安全/会返回什么与未知筛选漏判。该候选未 push、未发布。
新增跨领域及 speech-act 测试在首轮实现 21 failed / 8 passed。

整改撤回通用动词新增，改为完整闭合的周范围血氧请求投影，其他领域保持原有语义。
附加条件、引述/代码块/缩进材料、假设、撤回不匹配；原始请求另在 scope/gateway
拒绝未闭合的周血氧绘图，避免下游移除叙述片段后制造投影。
定向 125 passed；完整合跑结果与固定复审 SHA 在复审后确认。
