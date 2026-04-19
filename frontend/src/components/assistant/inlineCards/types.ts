/**
 * 动态聊天内联卡片系统 - 类型定义 (Web 版)
 * 与 mobile/components/chat/cards/types.ts 保持协议一致
 */
import type React from 'react';

export interface CardContext {
  query: string;
  query_lower: string;
  toolsUsed: Set<string>;
  data: {
    garmin?: any;
    score?: any;
    weather?: any;
    aqi?: any;
    profile?: any;
    [key: string]: any;
  };
  api: any;
}

export type MatchResult = number | null;

export interface CardSpec<D = any> {
  type: string;
  label: string;
  match(ctx: CardContext): MatchResult;
  build(ctx: CardContext): Promise<D | null> | D | null;
  render(data: D): React.ReactElement;
}

export interface ServerCardDescriptor {
  type: string;
  data: any;
}
