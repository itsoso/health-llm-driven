import { StyleSheet } from 'react-native';
import type { ColorPalette } from '../hooks/useTheme';
import { colors } from './theme';

/**
 * 主题感知的 markdown 样式 factory.
 *
 * 使用:
 *   const { c } = useTheme();
 *   const md = useMemo(() => createMdStylesChat(c), [c]);
 *   <Markdown style={md}>{content}</Markdown>
 *
 * 为什么是 factory: `react-native-markdown-display` 的 style prop 是静态对象,
 * 而 dark mode 下表头背景 / 边框 / 代码块底色都要跟着主题切换. 把样式写死成
 * 模块级常量在 light mode OK, 暗色下会出白亮的表头/代码块.
 */
export function createMdStylesChat(c: ColorPalette) {
  return StyleSheet.create({
    body: { fontSize: 15, lineHeight: 22, color: c.labelPrimary },
    heading1: { fontSize: 18, fontWeight: '700', color: c.labelPrimary, marginTop: 8, marginBottom: 4 },
    heading2: { fontSize: 16, fontWeight: '700', color: c.labelPrimary, marginTop: 6, marginBottom: 2 },
    heading3: { fontSize: 15, fontWeight: '600', color: c.labelPrimary, marginTop: 4 },
    strong: { fontWeight: '600', color: c.labelPrimary },
    em: { fontStyle: 'italic' },
    bullet_list: { marginVertical: 2 },
    ordered_list: { marginVertical: 2 },
    list_item: { flexDirection: 'row', marginVertical: 1 },
    bullet_list_icon: { color: c.labelSecondary, marginLeft: 4, marginRight: 6 },
    ordered_list_icon: { color: c.labelSecondary, marginLeft: 4, marginRight: 6 },
    code_inline: {
      backgroundColor: c.fill, borderRadius: 4, paddingHorizontal: 3,
      fontFamily: 'Menlo', fontSize: 13, color: c.brand,
    },
    fence: {
      backgroundColor: c.fill, borderRadius: 6, padding: 8,
      fontFamily: 'Menlo', fontSize: 12, marginVertical: 4, color: c.labelPrimary,
    },
    paragraph: { marginVertical: 2, color: c.labelPrimary },
    link: { color: c.brand },
    blockquote: {
      backgroundColor: c.fill, borderLeftWidth: 3, borderLeftColor: c.brand,
      paddingLeft: 10, paddingVertical: 4, marginVertical: 4,
    },
    hr: { backgroundColor: c.separator, height: StyleSheet.hairlineWidth, marginVertical: 8 },
    table: {
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
      borderRadius: 6, marginVertical: 6, minWidth: 320,
    },
    thead: { backgroundColor: c.fill },
    tbody: {},
    th: {
      paddingVertical: 6, paddingHorizontal: 8, fontWeight: '600',
      fontSize: 13, color: c.labelPrimary, flex: 1, minWidth: 80,
    },
    tr: {
      borderBottomWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
      flexDirection: 'row',
    },
    td: {
      paddingVertical: 6, paddingHorizontal: 8, fontSize: 13,
      color: c.labelPrimary, flex: 1, minWidth: 80,
    },
  });
}

export function createMdStylesCompact(c: ColorPalette) {
  return StyleSheet.create({
    body: { fontSize: 14, lineHeight: 20, color: c.labelPrimary },
    heading1: { fontSize: 17, fontWeight: '700', color: c.labelPrimary, marginTop: 6, marginBottom: 3 },
    heading2: { fontSize: 15, fontWeight: '700', color: c.labelPrimary, marginTop: 4, marginBottom: 2 },
    heading3: { fontSize: 14, fontWeight: '600', color: c.labelPrimary, marginTop: 3 },
    strong: { fontWeight: '600', color: c.labelPrimary },
    em: { fontStyle: 'italic' },
    bullet_list: { marginVertical: 2 },
    ordered_list: { marginVertical: 2 },
    list_item: { flexDirection: 'row', marginVertical: 1 },
    bullet_list_icon: { color: c.labelSecondary, marginLeft: 4, marginRight: 6 },
    ordered_list_icon: { color: c.labelSecondary, marginLeft: 4, marginRight: 6 },
    code_inline: {
      backgroundColor: c.fill, borderRadius: 4, paddingHorizontal: 3,
      fontFamily: 'Menlo', fontSize: 12, color: c.brand,
    },
    fence: {
      backgroundColor: c.fill, borderRadius: 6, padding: 8,
      fontFamily: 'Menlo', fontSize: 12, marginVertical: 4, color: c.labelPrimary,
    },
    paragraph: { marginVertical: 2, color: c.labelPrimary },
    link: { color: c.brand },
    blockquote: {
      backgroundColor: c.fill, borderLeftWidth: 3, borderLeftColor: c.brand,
      paddingLeft: 10, paddingVertical: 4, marginVertical: 4,
    },
    hr: { backgroundColor: c.separator, height: StyleSheet.hairlineWidth, marginVertical: 8 },
    table: {
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
      borderRadius: 6, marginVertical: 6, minWidth: 300,
    },
    thead: { backgroundColor: c.fill },
    tbody: {},
    th: {
      paddingVertical: 5, paddingHorizontal: 6, fontWeight: '600',
      fontSize: 12, color: c.labelPrimary, flex: 1, minWidth: 72,
    },
    tr: {
      borderBottomWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
      flexDirection: 'row',
    },
    td: {
      paddingVertical: 5, paddingHorizontal: 6, fontSize: 12,
      color: c.labelPrimary, flex: 1, minWidth: 72,
    },
  });
}

/**
 * 兼容旧调用 — 保留静态 export 但使用默认 light 色板.
 * @deprecated 新代码请用 createMdStylesChat(useTheme().c), dark mode 才正确.
 */
export const mdStylesChat = createMdStylesChat(colors);
export const mdStylesCompact = createMdStylesCompact(colors);
