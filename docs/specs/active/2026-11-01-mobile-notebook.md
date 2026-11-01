# Feature Spec: Mobile 私人记事本

> Status: implemented, local verification
> Owner: Codex
> Updated: 2026-11-01
> Related PRD: `docs/prd/2026-10-26-agenda-notebook.md`
> Related code: `mobile/components/life-navigation/NotebookPanel.tsx`

## 1. Decision

将现有 Web 私人记事本的读写能力提供给 Mobile，在个人安排中增加记事本标签。

## 2. Problem

Mobile 已保留 notebook 数据契约，但用户无法查看、搜索或编辑 Web 中保存的笔记。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 将 Web 记事本功能在 mobile 上实现
  classification: existing capability surface parity
  first_user_fit: 本人随手记录规划观察与反思
  core_loop_step: 观察和复盘
  first_class_objects: 延续既有私人规划工作区，不引入健康对象
  target_surface: Mobile 个人安排
  source_of_truth: authenticated life-navigation workspace
  safety_level: private planning write
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: 本人输入的纯文本
  claim_hedging: 不生成医学或因果结论
  verification_window: 保存确认后重新读取
  success_metric: 相同账号保存后重开可读，失败保留草稿
  added_user_burden: 手动点击保存
  burden_justification: 沿用现有工作区显式保存契约
  non_goals: AI 提取、自动健康记录、通知、新存储、发布
  smallest_end_to_end_slice: 打开记事本 → 新建 → 编辑 → 保存 → 重开
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

准入 PASS：既有用户需求的跨端补齐，沿用已批准 PRD 的私人规划边界。

## 4. Non-Goals

不新增 API、数据库迁移、AI 或后台采集。发布阶段按用户后续明确授权执行。

## 5. Product Object Mapping

沿用现有私人规划观察/反思数据。笔记不转为 HealthAgendaItem、HealthTwin 或医疗事实。

## 6. User Flow

个人安排 → 记事本列表 → 搜索/新建/打开 → 纯文本编辑 → 上方保存 → 后端版本确认。
列表和编辑器分屏呈现；返回列表保留草稿。搜索只影响列表，编辑对象由稳定 ID 绑定。
删除须原生确认，确认后仍需保存才写入。跨周切换不改变 notebook。

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | 本人笔记列表、编辑、搜索、删除 | 复用工作区保存、冲突、备份/恢复和会话生命周期 |
| Web | 现有记事本 | 使用同一 notebook 字段，无协议变化 |
| Backend | 认证隔离、持久化、版本竞争 | 现有 owner-scoped workspace CAS |

返回或侧滑退出时，未保存内容必须确认丢弃；保存中阻止返回。工作区的健康导航跳转同样需确认。后台隐藏正文，同会话返回恢复；账号切换立即清除，不被离页确认阻止。强制杀进程不在离页保护范围。没有将 Web 的工作区撤销/重做宣称为 Mobile 既有能力。

## 8. Data Contract

复用可选 `LifeData.notebook: NotebookEntry[]`。最多 100 条，标题 200 字符、正文 20000 字符，工作区整体 256 KiB；继续使用 `validateData`。旧工作区无 notebook 时呈现空列表，浏览不写回。

## 9. Safety, Privacy, And Medical Boundary

沿用 owner 参数、认证 API、revision CAS 与会话失效检查；无新日志、存储或导出出口。复用 Expo Router 已锁定的 React Navigation 7.2.2，以 usePreventRemove 拦截原生返回；package 与 lock 保持原生基线字节。
账号切换重建 Workspace；后台清空可见正文；延迟保存和删除确认必须通过现有 epoch/alive/active 检查。
保存中禁用编辑；失败保留草稿且不显示成功。正文通过 Text/TextInput 展示，不解释 HTML。

## 10. AI Behavior

无 LLM 调用，不自动提取健康事实或触发健康动作。

## 11. Acceptance Criteria

- Web 兼容工作区读入后能查看，修改和新建只在显式保存时发送同账号 revision。
- 搜索标题/正文忽略大小写和首尾空白；修改使标题不再匹配时，不切换编辑对象。
- 删除前确认；旧账号弹窗回调不得修改新账号数据。
- HTTP 409/500 保留草稿；保存成功后重开可读取。
- 后台正文不可见；同会话恢复；认证失效/换账号不得恢复旧草稿。
- 条数和输入上限生效；保存中禁止修改。

## 12. Verification Plan

```bash
cd mobile
npm test -- --runInBand components/life-navigation/__tests__/NotebookPanel.test.tsx app/__tests__/life-navigation.test.tsx services/__tests__/lifeNavigation.test.ts utils/__tests__/lifeNavigationModel.test.ts
./node_modules/.bin/tsc --noEmit
cd ..
./scripts/system-map-check.sh
git diff --check
```

测试使用合成数据和 API mock，不等同于真实账号生产保存或设备安装验证。

## 13. Rollout And Rollback

无迁移。授权发布后按项目 Mobile 发布闸执行；撤回 UI 不删除已保存 notebook 字段。

## 14. Open Questions

无阻断产品分叉。生产发布、真实跨端保存与模拟器人工验收单独记录证据。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-11-01 | Mobile notebook parity | 用户要求移动端支持 |
