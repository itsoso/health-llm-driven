# Dossier: 设置定位与入口全量审计

| 字段 | 值 |
|---|---|
| slug | `settings-location-navigation-audit` |
| 创建日期 | 2026-08-11 |
| 当前阶段 | S6（G3 PASS，待界面复验与发布） |
| 状态 | shipping |
| 负责 | Codex |
| 类型 | bugfix / mobile settings / navigation audit |
| 设计 | `docs/plans/2026-08-11-settings-location-navigation-audit-design.md` |
| 计划 | `docs/plans/2026-08-11-settings-location-navigation-audit.md` |

## 需求与现象

- 设置首页在 GPS 自动模式下优先显示省级 `region`，导致已经识别到城市时仍显示“浙江”而不是“杭州”。
- 回到设置页时不会主动刷新 profile，后台定位结果可能不能及时反映到界面。
- 自动定位执行状态不可见，用户无法区分“已自动更新”“等待权限”和“更新失败”。
- 设置入口较多，需要逐项验证生产可见链接，并修复行高、长文本和分隔线等一致性问题。

## G1 · 准入

- 对象: 用户 profile 中的定位偏好与检测结果；不新建健康对象。
- Surface: Mobile 设置页与现有 GPS 自动刷新 hook。
- 分类: 修复既有功能和可观测性，不改变医疗判断、数据授权范围或后端写入契约。
- **裁决: PASS。**

## G2 · 可行性与风险压测

- 根因 1: 设置页位置标签采用 `region ?? city`，优先级与“所在城市”的产品语义相反。
- 根因 2: 设置页重新获得焦点时没有失效 profile 查询。
- 根因 3: GPS hook 只有日志，没有供设置页消费的持久化状态。
- 方案: 手动城市优先；GPS 自动模式按 detected city → region → legacy city 回退；页面聚焦失效 profile；用 AsyncStorage 暴露非敏感刷新状态；为生产入口增加点击矩阵与静态路由存在性检查。
- 风险边界: 后台刷新仍不得主动弹权限；失败必须可见但不清空上次有效城市；不记录精确经纬度到新增状态存储。
- **裁决: PASS。**

## S5 · 实现

- [x] 修正 GPS 自动模式下城市/省份回退优先级。
- [x] 设置页重新获得焦点时刷新 profile。
- [x] 增加 idle / refreshing / ready / permission_required / error 状态并在设置页展示。
- [x] GPS 更新成功后失效设置页 profile，并实时推送刷新状态，关闭前台竞态与陈旧提示。
- [x] 节流命中恢复 ready 状态；Apple Health 与退出登录补齐点击面积和无障碍语义。
- [x] 增加 25 个生产可见入口的点击路由测试。
- [x] 增加设置页全部 39 条 push 路由的文件存在性检查。
- [x] 优化设置行高、长文本截断、状态布局与分组末行分隔线。

## G3 · 测试闸

- RED 已确认: 城市优先级、聚焦刷新、定位状态和生产入口点击矩阵在实现前按预期失败。
- GREEN 已确认:
  - 定向 Jest: 3 suites / 55 tests PASS。
  - TypeScript `npx tsc --noEmit`: PASS。
  - ESLint: 0 error；92 条为仓库既有 warning，本切片未新增 error。
  - `npm run check:settings-routes`: PASS，39 条设置 push 路由均存在。
  - `npm run design:check`: PASS，未新增设计令牌漂移。
  - iOS Release simulator build: PASS，0 error / 5 build warnings；已安装到 `Reva UI QA`。
- **裁决: PASS。**

## G4 · 评审闸

- 首轮独立 reviewer: BLOCK；指出 profile 缓存未失效、状态非响应式、节流不恢复 ready、Apple Health/退出登录点击面积与无障碍缺口，以及静态路由测试不能替代真实逐页加载。
- 已按前四项补回归并修复；待模拟器逐项点击复验后复评。

## G5 · 部署健康闸

- 待 production OTA 发布结果和更新元数据确认。

## G6 · 上线验证

- 待 production OTA 后冷启动确认：GPS 城市、状态文案及代表性设置入口。
