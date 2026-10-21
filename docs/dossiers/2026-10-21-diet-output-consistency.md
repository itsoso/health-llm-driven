# 文本与图片饮食记录结果一致性

## 范围与原因

修复现有结果展示，不新增记录权限或健康行为。文本 health_record 的质量层返回
record_quality，照片自动保存返回 diet_draft，导致同类已保存餐食使用不同布局、
数字精度与操作入口。

## 实现

- 有 verified 回执且 API 结果匹配当前 owner 时，文本输出 diet_draft 已记录卡；
  营养取保存结果（包括 null），展示统一两位小数，修正种子保留原精度。
- 历史文本卡只在 owner 绑定的记录回读成功后投影为统一餐食卡；不改写历史。
  待确认的修改提案、已删除或其他账号记录保持原有安全分支。
- 移动端复用餐食结果组件，保留个人提醒与下一步建议，取消强制整数读数。
- 回读清除旧建议时一并移除可重新注入旧建议的展开操作。

## 验证与交付

- RED：文本/图片契约比较失败（record_quality != diet_draft）；旧历史结果类型失败；
  Mobile 个人提醒用例失败。
- 第一轮 PostgreSQL：57 passed，覆盖真实认证 API 保存、回执、幂等重放、照片、
  owner 隔离与历史回读。所有样本为合成数据，未读取真实健康记录。
- Mobile：25 suites / 354 tests / 1 snapshot passed；TypeScript 检查通过。
- System Map 和 git diff --check 通过。最终 PostgreSQL 扩展回归及独立安全审查待完成。
- 发布尚未执行；须确认最新 main、精确 CI、安全 GO 及原发布状态后才能部署/OTA。
  当前共享工作区的其他任务改动保留，不进入本次提交。
