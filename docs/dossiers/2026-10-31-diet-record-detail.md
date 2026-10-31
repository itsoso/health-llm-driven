# 饮食记录详情与后续交互

- 用户原话：饮食记录要支持点击查看详情 以及进一步交互
- 当前阶段：S5，本地实现；未发布。
- 主流程：product-pipeline；S5 delegate：health-harness-orchestrator；overlay：safety-gate。
- 规格与验收：[feature spec](../specs/2026-10-31-diet-record-detail.md)。
- 现状：`mobile/app/diet.tsx` 列表正文是 View；已有 handleEdit、handleDelete、
  DietShareComposer、post_confirm 日复盘。复用这四条路径，无 API/数据库变化。
- G1：PASS，ExecutionEvent/HealthTwin/WriteIntent，饮食记录核对闭环；用户已授权实施。
- G2：PASS，使用详情 Modal 和已有操作；无新写自治或 AI 语义，无需额外产品决策。
- S4：组件与测试；列表接入及 owner/date 生命周期；回归与独立安全审查。
- Trace：`docs/_generated/harness-runs/ce0d7b4bc0c0.jsonl`（父 run）。
- G3 本地：PASS。先新增集成回归得到 10 failed（缺少详情入口），实现后详情组件、
  饮食页面、MealForm、分享组件和数字适配器合计 90 passed；全量 tsc、定向 ESLint、
  System Map、导航图及 doc drift、diff 检查通过。不是发布 CI-mode 集成闸。
- G4：待固定本地提交的独立安全审查。
- G5/G6：未执行。main ahead 5 / behind 126，已有并行未提交改动；按 AGENTS.md §7
  停止外部写入。保留上一项滚动修复和全部并行改动。

## 实现说明

- 记录正文/照片增加详情按钮，分享与估算重试保持独立触控区域。
- 详情按 owner/token/consent revision/date/record ID 绑定，从最新查询结果派生；
  账号、日期、同意或记录变化即清除。完整食物、照片、营养、备注与五项操作可访问。
- 修改沿用原子编辑并滚动到表单；删除保持确认与失败反馈，确认期间账号或同意变化
  会阻止写入。复盘复用既有后端本人记录查库协议，历史日期在徽标明确显示。
- 私有照片只接受 API 同源 URL；缺失和加载失败明确展示，提供重试。
- iOS 详情跳分享等待 Modal onDismiss，不同时展示两个原生 sheet。
- 未新增 API、数据库字段或识别/临床逻辑；未跑真实模型，复盘协议未改变。
- 当前修复包未完成模拟器视觉验收，组件事件测试不冒充设备验收。
