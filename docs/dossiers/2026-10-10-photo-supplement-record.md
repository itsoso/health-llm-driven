# 图片多补剂记录目标未绑定

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G2 图片候选确认方案，G3 报错局部修复 |

primary controller: health-harness-orchestrator；overlay: safety-gate。

## G1 准入
裁决：PASS。用户截图中“记录四种补剂 NAC 2粒 其他各1粒”带照片，收到 health_record_target_mismatch 的笼统名称或剂量缺失提示。要求准确记录已服用数量，不授予推断瓶身含量、换算剂量或凭模型自由描述自动写入的权限。

## 根因证据
- agent_executor._analyze_image_with_vision 对非餐食图片仅生成普通图片描述；描述进入模型messages，但不是绑定owner/source的结构化补剂候选。
- capability_policy._health_record_target_status依据用户原文目标核对名称与数量，不会把自由图片描述当用户授权。因而模型提出四种名称时可能与原文NAC及“其他”无法逐项对应。
- 当前无该截图对应线上完整工具trace；不能断定具体拒绝参数，更不能宣称四项已保存。
- 同图“分析刚才的运动”原代码误将“刚才”当非本人主体，独立只读复现；共享工作区已有另一session recent-workout修复，本线程不重复修改其文件。

## G2 方案与边界
待完整评审：结构化图片识别候选绑定当前用户、source message与图片；仅识别商品名称，不把标签每份含量当实际服用量。显式NAC2粒与其余各1粒需验证候选数量、NAC唯一匹配和单位；未知项保留未知并针对该项澄清。预览确认后走已有受控写入和逐项回执，失败/部分成功不能整体报成功。不得直接放宽target_mismatch或让OCR文字成为写权限。
缺少已授权真实模型评测入口的阻断仍在，不能以mock声称原图识别验证通过。图片批量记录完整功能尚未修复。

## G3 局部报错修复
先失败测试后修改：附图+补剂的target_mismatch说明“图片识别结果未能与本次要求逐项对应”，给出清晰标签或逐项名称数量的补充方式，明确未执行记录。其余target mismatch文案及所有写入校验不变。
未提交/未上线。待补真实流验证、独立审查及候选集成；本局部文案修复不算图片记录功能交付。

## 2026-10-10 聊天 UI 局部优化（未发布）

用户补充截图要求优化聊天界面，本次仅整理展示层，不更改补剂写入授权或失败判定。
- `ChatBubble`：全部图片具备可渲染 source 且尾部附件数吻合时，隐藏重复附件标记；保留原始消息用于复制、回放和无障碍。受保护图片无认证或数量不符时保留提示。
- `AnswerEvidencePanel`：没有详情且没有操作时不渲染空栏；只有处理日志时标题为“处理详情”，降低底色强调，真实来源和结构化依据仍为“回答依据”。技术耗时、模型、Token、失败详情继续可展开。
- 先新增失败测试，再做最小修改；初次 RED 包含三项目标行为失败，另一个复制按钮测试的标签写错已纠正。
- 最终相关 7 套 Jest / 166 项通过（`/tmp/reva-chat-ui-final.log`）；`npx tsc --noEmit` 通过（`/tmp/reva-chat-ui-tsc.log`）。
- 该组件未被 System Map selector 索引，已回到源码与实际组件测试核对。地图包装脚本因 PATH 无 python3.12 未能启动，另行直接执行现有 venv 下 checker。
- 无模拟器视觉验收、无固定 SHA CI、未提交/部署/OTA；继续遵守统一 owner 的提交冻结。

## 2026-10-10 外部 Agent 服用量契约补齐

用户新增截图：外部 Agent 宣称 NAC 2粒、其余各1粒已记录，却说明仅写入 taken。尚无该调用线上 trace，不能判定实际命中接口或补改历史记录。
代码确认数据库已有 `SupplementRecord.actual_dosage`，单条 `/api/v1/supplements/records` 和按名称 `/records/intake-batch` 均支持；旧按 ID `/records/batch` 的 item 缺字段且回执只有 action，形成接口能力不一致。

G2 局部方案 PASS：复用 actual_dosage，不新增 dosage_count、不迁移数据。按 ID 批量接口逐项接收明确实际服用量，返回落库 record_id/date/taken/actual_dosage。未提供时保留历史值；新记录未知量返回 null，不能据常规剂量/瓶身规格补全。本人校验仍在整批写入前；按现有同日唯一记录 upsert，不累加次数。日期由请求明确提供。旧数据不从截图自动回填。

客户端示例（合成 ID，仅说明接口）：
```json
{"record_date":"2026-10-10","checkins":[{"supplement_id":101,"taken":true,"actual_dosage":"2粒"},{"supplement_id":102,"taken":true,"actual_dosage":"1粒"}]}
```
回查 `/api/v1/supplements/me/date/{record_date}` 的 `record.actual_dosage`；不要读取 definition.dosage 当成本次数量。数量未落库时不得宣称该数量已记录。单条接口仍可使用已有 actual_dosage。

G3：两项新测试先 RED（422 拒绝 actual_dosage），实现后 SQLite 全部59项通过；继续补未知数量/非法载荷反例和真实 PostgreSQL 回读测试。OpenAPI 与 Web/Mobile 类型已由生成器同步。本局部契约修复不等于图片识别授权链路或外部 Noe 实测已完成。无提交/发布，遵守 owner 冻结。

### 数量契约本地收口证据
- SQLite最终64项通过，另补取消服用/显式null清除测试1项通过（共65项）；实际PostgreSQL首批59项通过并生成coverage（219.75s，`/tmp/reva-supp-dose-pg.log`），新增6项单独PG验证中。PG日志有测试schema drop/create期间后台scheduler查询已删除smart_reminders的噪声，不把这些日志当线上任务或业务验收证据。
- 两端API类型生成成功；Mobile与Web `tsc --noEmit` 均exit0；System Map直接checker与diff检查通过。最终生成变化仅新增批量请求数量字段、响应schema和说明；后一次重生成只更新字段注释。
- 独立安全文件预审GO，补null/取消语义后复审保持GO。非固定SHA G4，不代替完整CI/发布。审查确认并发首次插入仍可能触发现有唯一约束错误并返回失败；不得宣称并发无错重放。
- 数量仅凭显式请求落库；旧布尔接口调用不自动获得数量证明。外部Noe仍需刷新契约并提交actual_dosage、核对回执，未进行该端到端验证，也未回填用户历史记录。
- 最后新增6项真实PostgreSQL全部通过（`/tmp/reva-supp-dose-pg-final6.log`）；与首批59项合计覆盖65项，生产逻辑期间未变，仅补测试和OpenAPI字段说明。2026-10-10 12:22通过pg_ctl status确认测试PG已停止（no server running）。本地API契约修复完成，固定SHA审查、CI、部署及外部Agent实测仍待统一发布。
