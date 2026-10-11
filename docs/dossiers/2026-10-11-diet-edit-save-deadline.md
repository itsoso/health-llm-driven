# Dossier: 饮食修改保存等待上限

| 字段 | 值 |
|---|---|
| slug | diet-edit-save-deadline |
| 创建日期 | 2026-10-11 |
| 当前阶段 | G3 本地回归通过，等待独立G4 |
| 状态 | building |
| 负责 | root |

## 用户证据与诊断

用户截图：饮食记录修改拌面从1盘到2盘，按钮停在“保存中…”。现有路径 await 旧营养回填，再调用原子重估接口；Axios默认30秒仅限制已发出的HTTP请求，无法限制之前的revision join及异步拦截器。后端原子重估使用同步文字模型估算，未传已有可选timeout_seconds。截图本身不能确认具体等待阶段；今日固定journal窗口无匹配接口完成或文字超时事件，也不能证明请求未发生。

## 修复范围

## G1 准入

裁决: PASS。这是既有饮食人工编辑/确认路径的等待故障修复，保留健康观察、人工确认及写入回执边界；不增加健康建议或新数据用途。用户直接提供触发场景要求修复。

## G2 实现边界

裁决: PASS。复用现有原子重估、幂等和CAS；只增加客户端等待与取消边界，不以超时推断写入结果。

仅Mobile编辑保存路径新增覆盖全流程的35秒deadline及AbortSignal。旧回填晚到后先检查signal，禁止超时后才发送修正；已发出请求的晚到结果不得触发成功关闭或清除重试标识。原子重估和手动更新都传输signal，保留原CAS/幂等语义，不自动重发、不伪称未写入。超时恢复操作、保留修改，提示先核对记录再决定重试。等待时显示重新估算提示。没有改模型、营养推断、后端写入规则、接口schema或原生依赖。

## G3 验证

deadline测试先RED（缺少功能模块）后GREEN。新增屏幕回归覆盖用户“1盘→2盘”、永久pending、35秒恢复、传输abort、晚到结果及重试key；纯逻辑回归覆盖迟到revision join不得发送，以及成功/错误清理timer。五个Mobile suite43 passed，tsc exit0、System Map及diff-check通过。日志 `/tmp/reva-diet-edit-deadline-red.log`、`/tmp/reva-diet-edit-final.log`、`/tmp/reva-diet-edit-tsc-final.log`。未执行真实模型评测；无数据库变更。

## G4/G5/G6

待独立审查与发布。原始超时不等于服务端未写入；本轮不声称真实重估速度已改善或实际手机路径通过。默认后台模拟器验收；Mobile纯JS/TS候选满足闸后通过trusted OTA交付，发布阶段分别记录精确CI、后端部署、OTA及模拟器采用证据。
