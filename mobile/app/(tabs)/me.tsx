/**
 * "我" tab (2026-05-29).
 *
 * 直接复用 app/settings.tsx 的完整 hub (20+ 入口: AI 模型 / 个人画像 / 化验
 * / 用药 / 通知 / 家庭 / Garmin / Apple Health / Face ID / 退出). settings.tsx
 * 检测 router.canGoBack() 自动切换 "设置" / "我" 标题 + 隐藏返回按钮.
 *
 * 仍保留 /settings 路由 (EnvironmentCard 齿轮 push 进), 两条路径同一组件.
 * 选定 "我" tab 落定后可以考虑 EnvironmentCard 齿轮改 push /(tabs)/me 切 tab.
 */

export { default } from '../settings';
