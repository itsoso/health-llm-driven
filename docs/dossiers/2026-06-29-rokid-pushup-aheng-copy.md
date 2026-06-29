# Dossier: Rokid 俯卧撑教练阿衡文案收敛

| 字段 | 值 |
|---|---|
| slug | `rokid-pushup-aheng-copy` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile jest |

## S0 · 用户需求(逐字)

> 继续下一批

本切片承接本周计划中“单独处理 Rokid 专页旧称和相关测试”。先从较小且可验证的 `Rokid 俯卧撑计数` 页面入手,收敛用户可见旧称,不触碰 Rokid Health 大页和 SDK 技术契约。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `mobile/app/rokid-pushup-coach.tsx`:俯卧撑教练页面和 native setup failure 文案。
  - `mobile/app/__tests__/rokid-pushup-coach.test.tsx`:wrong CXR session mode 已有行为测试。
  - `mobile/constants/brand.ts`:已定义 `APP_DISPLAY_NAME = '阿衡'`。
- 缺口:
  - wrong session mode 提示仍显示“完全退出 Reva”和“不要先打开 Reva 眼镜视图”。
- 硬边界:
  - 不改 Rokid SDK 初始化、CustomApp / CustomView 状态机、native package、URL scheme、APK 安装流程。
  - 不把 `Rokid`、`CXR-L`、`CustomView`、`CustomApp` 等技术名替换为产品名。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`AssistantPersona`, `DeviceIntegration`, `ExecutionEvent`
- core_loop_step:快速记录俯卧撑 -> Rokid 眼镜识别或本地计数 -> 保存运动记录 -> 回到训练负荷判断。
- target_surface / safety_level / autonomy_tier:Mobile Rokid pushup coach / low(copy consistency) / read-only UI copy。
- spec_required(§8.1):否,不新增行为、写路径或安全规则。
- smallest_end_to_end_slice:替换 wrong session mode 用户提示旧称并加回归测试。
- stale_surface_to_remove:`Rokid 俯卧撑计数` 页面中的用户可见 `Reva`。
- 裁决:PASS。

## S2 · PRD

- 链接:`docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`
- 引用能力:快速记录、Rokid 低摩擦运动记录、统一产品人格。
- 不做:不重构 Rokid Health 大页、不改 SDK 契约、不新增设备能力。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-rokid-pushup-aheng-copy-plan.md`
- 任务:
  1. TDD:把 wrong session mode 测试期望改为 `阿衡` 并确认 RED。
  2. 实现文案替换,复用 `APP_DISPLAY_NAME`。
  3. 跑聚焦 Rokid pushup 测试。
  4. 跑 TypeScript、dossier/doc drift、diff check。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 风险:
  - Rokid/CXR-L 相关技术名不能误改,否则会混淆 SDK 状态和调试日志。
  - 只改文案,不触碰会话模式、安装流程、保存记录路径。
  - `Rokid Health` 大页测试面较大,留作后续独立切片。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 更新 `rokid-pushup-coach` wrong session mode 测试期望。
- [x] T2 修改 `formatRealPushupSessionIssue` 用户提示。
- [x] T3 运行聚焦测试。
- [x] T4 回写 plan / dossier / weekly plan。

## S5 · 实现

- `mobile/app/rokid-pushup-coach.tsx`:wrong session mode 提示改用 `APP_DISPLAY_NAME`。
- `mobile/app/__tests__/rokid-pushup-coach.test.tsx`:确认显示 `阿衡`,不显示旧称。

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath app/__tests__/rokid-pushup-coach.test.tsx --runInBand`
  - 预期失败:页面仍显示“完全退出 Reva”。
- PASS:同一命令。
  - 1 suite passed,15 tests passed。

## G4 · 安全闸

- 触发?:否。仅用户可见文案替换,不改变设备控制、运动记录写入或健康建议逻辑。
- 裁决:GO。

## S6 · 部署

- 本批未部署。属于 Mobile JS/TS/UI 文案变更,后续可随二维码包或 OTA 一起发布。

## G5 · 部署健康闸

- 本地测试闸通过。无线上部署。

## S7 · 上线验证

- 待后续真机/模拟器走查:wrong CXR session mode 提示显示 `阿衡`,且 Rokid 俯卧撑本地保存仍可用。

## G6 · 验证闸(人在环)

- 无新增人审阻塞。

## S8 · 沉淀

- 状态 -> **shipped-local-gate**。
- 后续:继续 Rokid Health 大页的用户可见旧称收敛,但保留 SDK/CustomView 技术命名。
