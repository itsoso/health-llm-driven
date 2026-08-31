/**
 * MarkdownText —— 共享 markdown 渲染薄包装 (2026-05-12).
 *
 * 默认用 createMdStylesCompact (卡片场景短文本). chat 场景可用 variant="chat".
 *
 * 用 react-native-markdown-display 渲染 **bold** / ## 标题 / - 列表 / GFM 表格.
 *
 * 2026-05-14: 加 preprocessTables — RN markdown lib 在 Expo 54 上偶尔 GFM 表格不渲染,
 * 我们显式把 `| h | h |` 转成 markdown 列表保证内容齐全可读.
 */

import React, { useMemo } from 'react';
import Markdown from 'react-native-markdown-display';
import { createMdStylesCompact, createMdStylesChat } from '../../constants/markdownStyles';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';
import { preprocessMarkdownTables } from '../../utils/markdownTables';
import { prepareSafeMarkdown, safeMarkdownIt } from '../../utils/safeMarkdown';

interface Props {
  children: string;
  variant?: 'compact' | 'chat';
  palette?: ColorPalette;
}

export default function MarkdownText({ children, variant = 'compact', palette }: Props) {
  const { c: themePalette } = useTheme();
  const c = palette ?? themePalette;
  const style = useMemo(
    () => (variant === 'chat' ? createMdStylesChat(c) : createMdStylesCompact(c)),
    [c, variant],
  );
  const processed = useMemo(
    () => prepareSafeMarkdown(preprocessMarkdownTables(children || '')),
    [children],
  );
  if (!children) return null;
  return <Markdown style={style} markdownit={safeMarkdownIt}>{processed}</Markdown>;
}
