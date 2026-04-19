/**
 * 动态卡片注册系统 - 类型定义
 *
 * 目标: 前端关键词/工具触发 + 后端主动下发 共用同一套卡片协议
 *
 * 扩展一张新卡片只需:
 * 1. 实现 CardSpec (id + match + build + render)
 * 2. 在 registry.tsx 里 push 进去
 * 3. 后端可在 SSE done 事件里塞 cards: [{type, data}]  自动渲染
 */

import type React from 'react';

/** 卡片运行时上下文 - 给 build() 拉数据用 */
export interface CardContext {
  /** 用户原始输入 */
  query: string;
  query_lower: string;
  /** 此次对话用到的工具名集合 (health_record / get_health_data / ...) */
  toolsUsed: Set<string>;
  /** 已经缓存在 React Query 里的各种 data (只读快照) */
  data: {
    garmin?: any;
    score?: any;
    weather?: any;
    aqi?: any;
    weight?: any;
    supplement?: any;
    bp?: any;
    rhinitis?: any;
    [key: string]: any;
  };
  /** API 客户端, 用于 build() 里按需拉数据 */
  api: any;
}

/** match() 返回值: null=不触发; number=优先级 (高者赢) */
export type MatchResult = number | null;

export interface CardSpec<D = any> {
  /** 卡片唯一标识, 也是 <message>.cardType 的值 */
  type: string;
  /** 人类可读名 */
  label: string;
  /**
   * 是否触发这张卡片. 返回 null/undefined 不触发; 返回数字是优先级
   * 多张卡片都命中时, 取优先级最高的一张
   */
  match(ctx: CardContext): MatchResult;
  /**
   * 组装卡片 data. 返回 null = 数据不足放弃渲染
   * 允许 async, 会按需拉数据
   */
  build(ctx: CardContext): Promise<D | null> | D | null;
  /** 渲染组件 */
  render(data: D): React.ReactElement;
}

/** 后端下发的卡片描述 (SSE done 事件里的 cards 字段) */
export interface ServerCardDescriptor {
  type: string;
  data: any;
}
