# Dossier: Rokid Health 大页阿衡文案收敛

| 字段 | 值 |
|---|---|
| slug | `rokid-health-aheng-copy` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile jest |

## S0 · 用户需求(逐字)

> 继续

本切片承接本周计划中“单独处理 Rokid 专页旧称和相关测试”。前一批已收敛 Rokid 俯卧撑教练,本批处理测试面更大的 `Rokid 眼镜健康模式` 大页。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `mobile/app/rokid-health.tsx`:Rokid Health 大页,含授权、CustomView、语音控制、拍照和诊断。
  - `mobile/app/__tests__/rokid-health.test.tsx`:覆盖 iOS 授权、CustomView 打开、NoNetwork、BLE pending、语音控制等 42 个测试。
  - `mobile/constants/brand.ts`:已定义 `APP_DISPLAY_NAME = '阿衡'`。
- 缺口:
  - 页面按钮、等待态、失败态、授权回调提示和 CustomView payload 仍显示 `Reva`。
  - 语音控制 CustomView 标题仍显示 `Reva 语音控制`。
- 硬边界:
  - 不改 Rokid SDK 授权 `appName: 'Reva'`。
  - 不重命名 `openRokidRevaCustomView` / `createRokidRevaCustomViewLayout` 等技术函数。
  - 不改 `Reva build`、`appName=Reva` 等历史诊断字段,确保现场日志仍可对照。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`AssistantPersona`, `DeviceIntegration`, `ExecutionEvent`
- core_loop_step:用户打开 Rokid Health -> 授权/打开眼镜视图 -> 低摩擦记录饮食/运动 -> 反馈到健康日序。
- target_surface / safety_level / autonomy_tier:Mobile Rokid Health / low(copy consistency) / read-only UI copy。
- spec_required(§8.1):否,不新增行为、写路径、自动化决策或安全规则。
- smallest_end_to_end_slice:替换 Rokid Health 用户可见旧称并加回归测试。
- stale_surface_to_remove:`Rokid 眼镜健康模式` 页面和眼镜端 CustomView payload 中的用户可见 `Reva`。
- 裁决:PASS。

## S2 · PRD

- 链接:`docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`
- 引用能力:Rokid 低摩擦记录、Chat/动态卡片驱动、统一产品人格。
- 不做:不改变外设 SDK 状态机、不新增真机能力、不扩大自动写入。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-rokid-health-aheng-copy-plan.md`
- 任务:
  1. TDD:把 Rokid Health 用户可见旧称测试期望改为 `阿衡` 并确认 RED。
  2. 实现文案替换,复用 `APP_DISPLAY_NAME`。
  3. 跑聚焦 Rokid Health 测试。
  4. 跑 TypeScript、dossier/doc drift、diff check。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 风险:
  - Rokid/CXR-L/CustomView 技术名误改会破坏 SDK 诊断和历史日志比对。
  - `appName: 'Reva'` 可能参与 native 授权语义,本批不改。
  - 只替换用户可见文案和 CustomView 展示 title/body,不改设备控制、语音、拍照或写记录逻辑。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 更新 `rokid-health` 用户可见旧称测试期望。
- [x] T2 修改授权、CustomView、语音控制、页面按钮和诊断指引文案。
- [x] T3 运行聚焦 Rokid Health 测试。
- [x] T4 回写 plan / dossier / weekly plan。

## S5 · 实现

- `mobile/app/rokid-health.tsx`:引入 `APP_DISPLAY_NAME`,替换用户可见 `Reva` 文案和 CustomView 展示 title/body。
- `mobile/app/__tests__/rokid-health.test.tsx`:更新 Rokid Health 品牌一致性期望。

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath app/__tests__/rokid-health.test.tsx --runInBand`
  - 预期失败:实现仍显示 `Reva`,测试期望 `阿衡`。
- PASS:同一命令。
  - 1 suite passed,42 tests passed。
  - 仍有既有 React act warning,不影响退出码;本批未扩大该 warning。

## G4 · 安全闸

- 触发?:否。仅用户可见文案和 CustomView 展示文案替换,不改变设备控制、L3 音频采集、拍照、用药/补剂/饮食写入或权限逻辑。
- 裁决:GO。

## S6 · 部署

- 本批未部署。属于 Mobile JS/TS/UI 文案变更,后续可随二维码包或 OTA 一起发布。

## G5 · 部署健康闸

- 本地测试闸通过。无线上部署。

## S7 · 上线验证

- 待后续真机/模拟器走查:Rokid Health 大页按钮、会话状态、眼镜端 CustomView 标题/正文和失败引导显示 `阿衡`。

## G6 · 验证闸(人在环)

- 无新增人审阻塞。

## S8 · 沉淀

- 状态 -> **shipped-local-gate**。
- 后续:继续处理截图/审核材料、主屏视觉走查、Chat card action 成功反馈和 Watch/二维码发布条件。
