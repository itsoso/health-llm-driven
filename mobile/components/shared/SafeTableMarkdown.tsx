import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { useTheme } from '../../hooks/useTheme';
import { revaFonts } from '../../constants/revaTheme';
import { preprocessMarkdownTables } from '../../utils/markdownTables';
import { prepareSafeMarkdown, safeMarkdownIt } from '../../utils/safeMarkdown';
import { splitHtmlTableContent, type SafeHtmlTable } from '../../utils/safeHtmlTable';
import { parseSafeHtmlDocument, type SafeHtmlDocument } from '../../utils/safeHtmlDocument';

function TablePreview({ table, source }: { table: SafeHtmlTable; source: string }) {
  const { c } = useTheme();
  const [sourceVisible, setSourceVisible] = useState(false);
  return (
    <View testID="safe-html-table" style={[styles.container, { borderColor: c.separator }]}>
      {table.caption ? <Text style={[styles.caption, { color: c.labelPrimary }]}>{table.caption}</Text> : null}
      <ScrollView horizontal showsHorizontalScrollIndicator nestedScrollEnabled accessibilityLabel="数据表格，可左右滑动查看各列">
        <View>
          {table.rows.map((row, rowIndex) => (
            <View key={rowIndex} style={styles.row}>
              {row.map((cell, columnIndex) => (
                <View key={columnIndex} testID={`safe-html-cell-${rowIndex}-${columnIndex}`} style={[styles.cell, {
                  borderColor: c.separator,
                  backgroundColor: cell.header ? c.fill : c.bgCard,
                }]}>
                  <Text selectable accessibilityRole={cell.header ? 'header' : undefined}
                    style={[styles.text, { color: c.labelPrimary, fontWeight: cell.header ? '600' : '400' }]}>
                    {cell.text}
                  </Text>
                </View>
              ))}
            </View>
          ))}
        </View>
      </ScrollView>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: sourceVisible }}
        onPress={() => setSourceVisible(visible => !visible)} style={styles.disclosure}>
        <Text style={{ color: c.brand, fontSize: 13 }}>{sourceVisible ? '收起 HTML 源码' : '查看 HTML 源码'}</Text>
      </Pressable>
      {sourceVisible ? <Text selectable style={[styles.source, { color: c.labelSecondary }]}>{source}</Text> : null}
    </View>
  );
}

function DocumentPreview({ document, source }: { document: SafeHtmlDocument; source: string }) {
  const { c } = useTheme();
  const [sourceVisible, setSourceVisible] = useState(false);
  return <View testID="safe-html-document" style={[styles.container, { borderColor: c.separator }]}>
    <Text style={[styles.caption, { color: c.labelSecondary }]}>HTML 文档（安全阅读模式）</Text>
    {document.blocks.map((block, index) => <Text key={index} selectable
      accessibilityRole={block.kind === 'heading' ? 'header' : undefined}
      style={[styles.text, styles.disclosure, { color: c.labelPrimary, fontWeight: block.kind === 'heading' ? '600' : '400', paddingLeft: 12 + (block.depth ?? 0) * 16 }]}>
      {block.kind === 'list' && block.marker ? `${block.marker} ${block.text}` : block.text}
    </Text>)}
    <Pressable accessibilityRole="button" accessibilityState={{ expanded: sourceVisible }}
      onPress={() => setSourceVisible(visible => !visible)} style={styles.disclosure}>
      <Text style={{ color: c.brand, fontSize: 13 }}>{sourceVisible ? '收起 HTML 源码' : '查看 HTML 源码'}</Text>
    </Pressable>
    {sourceVisible ? <Text selectable style={[styles.source, { color: c.labelSecondary }]}>{source}</Text> : null}
  </View>;
}

type Props = Pick<React.ComponentProps<typeof Markdown>, 'style' | 'rules'> & {
  content: string;
  allowHtmlTables?: boolean;
};

/** Render tables using native text only. HTML stays disabled in Markdown. */
export default function SafeTableMarkdown({ content, style, rules, allowHtmlTables = true }: Props) {
  const { c } = useTheme();
  const safeContent = prepareSafeMarkdown(content);
  const parts = useMemo(() => splitHtmlTableContent(safeContent), [safeContent]);
  // Streaming retains source even if an early table is already closed, while
  // keeping the existing loose-Markdown cleanup for ordinary prose.
  return <>{parts.map((part, index) => {
    if (allowHtmlTables && part.kind === 'table') return <TablePreview key={index} table={part.table} source={part.source} />;
    const document = allowHtmlTables && part.kind === 'source' ? parseSafeHtmlDocument(part.source) : null;
    if (document) return <DocumentPreview key={index} document={document} source={part.source} />;
    if (allowHtmlTables && part.kind === 'source') return (
      <View key={index} style={[styles.container, { borderColor: c.separator }]}>
        <Text style={[styles.disclosure, { color: c.labelSecondary }]}>HTML 源码（暂不支持此格式预览）</Text>
        <Text selectable style={[styles.source, { color: c.labelPrimary }]}>{part.source}</Text>
      </View>
    );
    return <Markdown key={index} style={style} rules={rules} markdownit={safeMarkdownIt}>
      {part.kind === 'markdown' ? preprocessMarkdownTables(part.source) : part.source}
    </Markdown>;
  })}</>;
}

const styles = StyleSheet.create({
  container: { marginVertical: 8, borderWidth: StyleSheet.hairlineWidth, borderRadius: 8, overflow: 'hidden' },
  caption: { fontSize: 15, fontWeight: '600', padding: 12 },
  row: { flexDirection: 'row', alignItems: 'stretch' },
  cell: { width: 132, paddingHorizontal: 12, paddingVertical: 10, borderRightWidth: StyleSheet.hairlineWidth, borderBottomWidth: StyleSheet.hairlineWidth },
  text: { fontSize: 14, lineHeight: 21 },
  disclosure: { paddingHorizontal: 12, paddingVertical: 12 },
  source: { fontFamily: revaFonts.mono, fontSize: 12, lineHeight: 18, padding: 12 },
});
