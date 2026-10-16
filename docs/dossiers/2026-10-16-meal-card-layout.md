# 餐食卡片视觉整理

| Field | Value |
| --- | --- |
| status | building |
| current_stage | G3 verification / G4 review |
| Controller | quick_fix |

## G1 Scope admission

裁决: PASS。现有餐食卡视觉修正，不增加用户行为、健康建议或写权限。

## 范围

仅调整 `mobile/components/chat/cards/DietDraftCard.tsx` 的视觉层，不改识别、记录、确认、数据计算、健康建议或导航行为。保留其他会话修改。

## 实现

- 营养区从无列间距的行改为两列独立单元，标签与读数分行，避免左列数值贴住右列圆点。
- 增加食物标签行间距，调浅卡片底色。
- 保留底部查看和修正入口，以浅绿色区分查看入口。

## 验证

- TypeScript `tsc --noEmit` 通过。
- 卡片注册与交互回归：103 项通过。
- 实际组件 React Native Web 合成数据预览：390px 下内容和按钮可见；使用本地图片/路由适配，不代表 iOS 原生或真机验收。
- 本次未请求真实模型，未读取真实健康数据，未备份。

## 发布

待精确候选 CI、发布准入与回执；不得将本地验证声明为已上线。
