# 体检解读返回与继续讨论回归

| 字段 | 值 |
| --- | --- |
| 当前阶段 | S5 修复与回归 |
| 状态 | building |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |
| Run | `docs/_generated/harness-runs/5b5be9f937ce.jsonl`（本地） |

## G1 / G2

裁决: PASS。修复既有体检解读页面返回主会话和只读继续解读能力，不增加自主诊断、
开药或健康记录写权限。主对象为既有体检记录和会话上下文，认证后端仍为数据真源。
用户截图中的“最近一周”读取拒绝一并核对既有修复，不扩大部署或发布权限。

## S5 范围

- Mobile：体检解读页面退出、主屏会话导航及上下文传递，先补失败测试。
- Backend：复现内置提示词被临床来源护栏误拦截，保留真实临床依据复合写操作的拒绝。
- 保留其他任务的前端发布恢复档案与 Android 构建现场，不修改生产健康数据。
- 外部 TDD/verification 能力未在本会话提供；使用仓库 RED/GREEN 与新鲜验证，
  不调用禁用的 superpowers。

## G3 / G4

- UI 根因：原页面仅成功时声明原生 header，加载/失败没有退出；讨论按钮 push
  主会话，保留上层 modal。改为固定页头覆盖各状态，并仅此入口 opt-in dismissTo，
  携带相同提示词、报告上下文、badge 和新会话参数。RED 6 failed/1 passed；
  三组 Mobile 回归 29 passed，TypeScript exit 0；未做模拟器原生验收。
- Backend 复现内置提示词为 `unresolved_clinician_action`：名词“复查安排”加
  “向医生确认的问题”误入动作拒绝。局部只读问诊问题准备分类不覆盖医生转述、
  临床依据变更或独立写动作；真实写权限仍由原 capability policy 裁决。
- 先测出现 5 failed/19 passed：四个只读用例失败；第五个是测试错误要求原有
  zero-tool clinician_context 必须命名为 ambiguous，修正为验证原零工具安全语义，
  未改变产品分类来迎合测试。组合回归 1719 passed，包含完整 run_stream 的
  上下文、输出与无写入回执验证，以及第三张截图“最近一周”的现有范围回归。
- 运行时测试使用受控模型 stub 和合成数据，不是实际模型医疗答案质量证明。
  没有 schema/API 变更，不把 SQLite 用作生产数据库语义证据。
- LLM change gate passed / live_required=false；结构、地图、秘密扫描通过。
  固定提交独立安全审查待执行；当前不宣称全部发布闸通过。

### 独立复审回退

固定 `017d2aa0e` 相对 `1bdd64af1` 的独立 G4 NO-GO：问题清单之后的命令式
“把复查安排在明天上午八点”和含零宽字符的修改命令可能被新只读例外接受。
写工具能力探针仍拒绝，不声称发生数据库越权；但丢失确定性零工具拒绝本身即阻断。
新增前缀/后缀反例先得到 6 failed/4 passed；修复将 deny-only 动作规范化扫描扩展到
所有分句，并把名词例外限制到医生对象之前、同一问题准备分句的明确列表位置。
需完整重跑与新固定提交复审，不沿用旧 GO。保留原 NO-GO 与失败证据。

首轮护栏覆盖率 97%（616 passed）；Ruff 最初报三处 import 排序问题，机械修复后通过。
本机有 iOS 26.5 模拟器，但默认 xcrun 指向 CommandLineTools；仅以局部
DEVELOPER_DIR 确认可用，未改全局配置。已安装应用不是本轮候选，未把它作为验收证明。

## G5 / G6

未部署，未宣称线上或模拟器验收完成。
