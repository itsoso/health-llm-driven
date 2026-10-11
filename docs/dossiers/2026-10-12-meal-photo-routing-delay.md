# Dossier: 拍照记餐路由等待修复

| 字段 | 值 |
|---|---|
| slug | meal-photo-routing-delay |
| 日期 | 2026-10-12 |
| 当前阶段 | G6 后端部署核对完成 |
| 状态 | complete |
| 负责 | root |

## G1 准入

裁决: PASS。用户报告刚才拍照记餐9秒，比之前慢；修复既有记录执行等待，不新增健康建议或数据用途。继续遵守无需真实模型评测的直接指令。

## 同请求基线

生产后端bd7a2a49b，07:02这轮唯一diet_photo日志与该认证owner绑定的只读perf投影相互核验，无图片/正文/资源ID输出：可选Laya路由5034ms后timeout回退，vision provider2969ms、decode5ms；vision阶段3323ms，pre_llm8889ms、保存回执可见8941ms，最终对话31770ms。前置阶段之和不能说明全部客户端耗时；9秒与回执8941ms相符，图片上传和相机时长尚未定位。不拿不同照片旧均值当退化证明。

## G2 实现范围

裁决: PASS。明确Mobile拍照记餐、带图片、语义为记录且无只读/临床建议/文件时，可选决策层不增加识别或写权限，应无需等待。保留确定性tier、用户模型、vision完整识别、图片资产/记录原子保存、owner、取消、未知份量确认、幂等与回执。普通图片分析及非照片流程仍走原路由。追加路由阶段纯数字计时以避免漏记前置等待。质量底线：任何非食物/低置信/取消/分析请求不得因跳过建议层转为写入；不承诺所有照片低于固定秒数。失败或边界回归回退本次guard，不换模型/降图片质量/减识别规则。

## G3 验证

裁决: PASS。

实际stream路径先RED，因明确记餐仍调用可选路由；修订后403 passed、1 skipped，低置信仍产生确认草稿、无自动饮食写入。闭合记录指令才跳过，分析/混合建议/取消/其他记录/文件/只读/临床建议11项正反边界通过。普通决策层和fast routing回归通过，纯数字routing_ms进入既有Record类型perf，无API/schema改变。离线invariants/health_agent_core回归Gate通过，System Map与diff-check通过；真实模型调用0。符合用户长期豁免，但LLM变更门只以固定SHA waiver记录，不伪造live确认。证据 `/tmp/reva-meal-route-red.log`、`/tmp/reva-meal-route-green.log`、`/tmp/reva-meal-route-offline-gate.json`。

## G4 审查

裁决: PASS。a75d2e661固定候选独立GO，1288 passed、1 skipped。运维独立审查发现日志持久化和bytecode加载边界后修复，第三次全新审查GO；全部失败证据保留。

## G5/G6 交付

裁决: PASS。精确a75d2e661完整CI 38183804992 success，本地CI-mode 3593 passed、22 skipped、84 subtests passed。可信后端发布38185005589 success，服务器completed.json同SHA SUCCEEDED，部署仓库干净、四服务active、外网health200/healthy，无发布lease。首次old revoke入口用错路径，在任何写入前被固定路径校验拒绝；只读核对授权未变，独立GO后使用old canonical入口完成，不覆盖原失败日志。新修复后实际用户拍照提速尚未验证，不宣称9秒变为具体值。本次后端修改不需要OTA，真实模型评测按用户长期豁免保持0调用。私有证据索引 docs/reviews/2026-10-12-meal-photo-routing-release-receipt.json。
