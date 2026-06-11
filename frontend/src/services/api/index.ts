/**
 * API 服务入口 - Barrel Re-export (backward compatibility)
 *
 * 新代码应直接从子模块导入 (e.g. @/services/api/health)。
 * 本文件保留用于测试 mock 和少量遗留引用。
 */
export { api, API_BASE_URL } from './client';
export * from './health';
export * from './records';
export * from './user';
export * from './devices';
export * from './ai';
export * from './social';
export * from './content';
export * from './family';
export * from './personalOutcome';
export * from './safety';
export * from './orchestrator';
export * from './actionCard';
export * from './prescriptions';
