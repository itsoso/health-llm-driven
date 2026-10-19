# 普通照片用途修复

Updated: 2026-10-19
Status: local regression passed; PostgreSQL and G4 pending; not deployed
Spec: `docs/specs/active/2026-10-19-general-photo-purpose.md`
Workflow: quick_fix, safety overlay; no superpowers skills used.

## 故障与根因

普通照片会先尝试结构化食物识别；空说明或默认分析提示还可走高置信度隐式记餐。单独增加皮肤关键词不能消除默认食物假设。
Mobile 普通附件发送默认分析提示，明确拍照记餐才携带餐食上下文；后端产生截图中的餐食进度。
本轮只读核实生产 HEAD 为 `1ba724dcb62ac389a72e41eecf40fea7aaca27e3`，不包含已提交的皮肤排除修复 `c7616c88e`，因此已有本地排除不能证明用户线上问题解决。

## 准入与实现

G1: PASS，普通附件默认用途纠错，沿用 ExecutionEvent / WriteIntent；不新增数据类型、诊断能力或写授权。
识别、进度、结构化食物入口和实际 capture 共用正向餐食用途检查。普通空/默认照片使用通用视觉或原图多模态，不生成餐食进度或饮食记录/草稿。
明确餐食和明确记餐入口保留结构化识别、校准、权限、确认、幂等与回执。当前非餐食文本覆盖旧记餐上下文；报告和补剂继续独立预处理。
普通照片即使模型提出饮食写入，也由每轮写入边界拒绝；图片与聊天消息仍正常保存。

## 验证证据

- RED: 新增测试首轮 13 failed / 9 passed，复现默认食物调用及误捕获路径；日志 `/tmp/reva-general-photo-red.log`。
- 中间回归 16 failed / 257 passed / 1 skipped 保留。修正取消原因回传，并将旧空说明餐食 fixture 明确绑定记餐入口；未知体重附件不再要求食物上下文。
- GREEN: 普通照片新测试及食物识别、capture policy/service、图片生命周期、补剂图片回归 **371 passed / 1 skipped**；日志 `/tmp/reva-general-photo-regression.log`。
- System Map、mobile-nav、doc-drift 和 `git diff --check` 通过；没有结构生成物变化。
- PostgreSQL 独立 UTF8 数据库验证运行中；不以 SQLite 代替生产数据库语义。
- 图片和模型回复均为合成 fixture。未发送用户照片给模型，未读取生产健康记录；没有真实模型质量、生产用户或模拟器验收证据。

## 发布边界

仅修改本任务文件，保留共享工作区其他改动。开工时本地主干 ahead 5；最新只读远端 main 已推进到 `9d80d2d46f826ed023291a0d010be8d2e2acf3be`。
G4 待固定提交独立安全审查；G5 精确候选完整 CI/CI-mode、既有发布阻断收口与发布准入未完成。未推送、未部署，不能宣称用户线上已修复。
本任务只有后端改动，无需 Mobile OTA；未备份、未重放既有失败发布或维护操作。
