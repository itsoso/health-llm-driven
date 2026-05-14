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
// @ts-ignore — markdown-it 没有 bundled types, instance 用作运行时配置
import MarkdownIt from 'markdown-it';
import { createMdStylesCompact, createMdStylesChat } from '../../constants/markdownStyles';
import { useTheme } from '../../hooks/useTheme';

const mdInstance = MarkdownIt('default', {
  typographer: true,
  breaks: false,
  linkify: true,
  html: false,
});

const isRow = (s: string) => /^\s*\|.*\|\s*$/.test(s);
const isSep = (s: string) => /^\s*\|[\s\-:|]+\|\s*$/.test(s);
const splitRow = (s: string) =>
  s.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());

/**
 * GFM 表格 → markdown 列表.
 *   | 时间 | 动作 | 原理 |
 *   |------|------|------|
 *   | 晨起 | 戴口罩 | 防冷空气 |
 * →
 *   **时间 · 动作 · 原理**
 *   - **晨起** · 戴口罩 · 防冷空气
 */
function preprocessTables(md: string): string {
  const lines = md.split('\n');
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const next = lines[i + 1];
    if (isRow(line) && next && isSep(next)) {
      const headers = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isRow(lines[i]) && !isSep(lines[i])) {
        rows.push(splitRow(lines[i]));
        i++;
      }
      out.push('**' + headers.join(' · ') + '**');
      for (const r of rows) {
        const first = r[0] ? `**${r[0]}**` : '';
        const rest = r.slice(1).filter(Boolean).join(' · ');
        out.push(`- ${first}${first && rest ? ' · ' : ''}${rest}`);
      }
      out.push('');
      continue;
    }
    out.push(line);
    i++;
  }
  return out.join('\n');
}

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
  const processed = useMemo(() => preprocessTables(children || ''), [children]);
  if (!children) return null;
  return <Markdown style={style} markdownit={mdInstance}>{processed}</Markdown>;
}
