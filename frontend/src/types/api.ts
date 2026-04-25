/**
 * 类型化 API helpers — 基于 openapi-typescript 生成的 schema
 *
 * 用法:
 *   import type { components, paths } from '@/types/api';
 *
 *   // schema 类型 (各 endpoint 的请求/响应)
 *   type ConsultationDetail = components['schemas']['HealthConsultationDetail'];
 *
 *   // path 类型 (用 createClient 时)
 *   type Paths = paths;
 *
 *   // 取某 endpoint 200 响应:
 *   type Sleep200 = paths['/api/v1/garmin-analysis/me/sleep']['get']['responses'][200]['content']['application/json'];
 *
 * 重新生成:
 *   npm run generate-types
 *   (后端改 schema 后必跑)
 */
export type { components, paths, operations } from './api.generated';
