/**
 * API 服务入口 - Barrel Re-export
 *
 * 实际实现已拆分为领域模块：
 * - api/client.ts: Axios 实例 + 拦截器
 * - api/health.ts: 健康数据、分析、评分、报告
 * - api/records.ts: 打卡、补剂、排泄、睡眠、情绪、用药
 * - api/user.ts: 用户、引导、成就、目标、导出、通知
 * - api/devices.ts: Garmin、Withings 设备
 * - api/ai.ts: AI 对话、OpenClaw、单词本
 * - api/social.ts: 好友、私信、群聊、PK、积分、活动状态
 * - api/content.ts: 体检、疾病、新闻、饮食推荐、运动指导、儿童
 *
 * 本文件作为兼容层，所有现有 import 无需修改。
 */
export { default as api, API_BASE_URL } from './api/client';
export * from './api/health';
export * from './api/records';
export * from './api/user';
export * from './api/devices';
export * from './api/ai';
export * from './api/social';
export * from './api/content';
export * from './api/family';
export * from './api/personalOutcome';
