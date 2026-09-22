# 小巴健康 · 这一路 PRD

> Status: approved (G2 GO, implementation verification in progress); Updated: 2026-09-22

引用全局 `docs/prd/reva-personal-health-os-prd.md` R9 Review、R10 Mobile
与 `docs/specs/reva-product-governance-spec.md` 的低负担、自主、证据诚实原则。
用户已选择完整版（单次定位＋手动城市＋月度回顾＋分享长图，新安装包）。

## 四问

1. 谁用：已有记录的出差用户，希望看见奔波中的生活与自我照顾。
2. 解决什么：照片/餐食/生活事件分散，回顾缺时间地点上下文。
3. 数据流：本人源记录 -> 确认城市和日期 -> 事件地点注释 -> 月度 Review
   -> 明确勾选/去敏投影 -> 长图预览 -> 系统分享。
4. 边界：不全天追踪、不重建日记、不推断医疗/心理结论，不用里程评价用户。

完整行为、API、安全与验收以
`docs/specs/active/2026-09-22-monthly-journey.md` 为单一真源。
产品成功先看能否核对/更正、是否愿意保存回顾，不追求打开时长或强制打卡。
周报、动画及真实路线均延后，不在此版暗中扩展。
