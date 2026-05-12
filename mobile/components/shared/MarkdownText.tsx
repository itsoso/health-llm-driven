/**
 * MarkdownText —— 共享 markdown 渲染薄包装 (2026-05-12).
 *
 * 默认用 createMdStylesCompact (卡片场景短文本). chat 场景可用 variant="chat".
 *
 * 用 react-native-markdown-display 渲染 **bold** / ## 标题 / - 列表.
 */

import React, { useMemo } from 'react';
import Markdown from 'react-native-markdown-display';
import { createMdStylesCompact, createMdStylesChat } from '../../constants/markdownStyles';
import { useTheme } from '../../hooks/useTheme';

interface Props {
  children: string;
  variant?: 'compact' | 'chat';
}

export default function MarkdownText({ children, variant = 'compact' }: Props) {
  const { c } = useTheme();
  const style = useMemo(
    () => (variant === 'chat' ? createMdStylesChat(c) : createMdStylesCompact(c)),
    [c, variant],
  );
  if (!children) return null;
  return <Markdown style={style}>{children}</Markdown>;
}
