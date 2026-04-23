import { StyleSheet } from 'react-native';
import { colors } from '@/constants/theme';

export const mdStylesChat = StyleSheet.create({
  body: { fontSize: 15, lineHeight: 22, color: colors.labelPrimary },
  heading2: { fontSize: 16, fontWeight: '700', color: colors.labelPrimary, marginTop: 6, marginBottom: 2 },
  heading3: { fontSize: 15, fontWeight: '600', color: colors.labelPrimary, marginTop: 4 },
  strong: { fontWeight: '600' },
  bullet_list: { marginVertical: 2 },
  list_item: { flexDirection: 'row', marginVertical: 1 },
  code_inline: { backgroundColor: '#F2F2F7', borderRadius: 4, paddingHorizontal: 3, fontFamily: 'Menlo', fontSize: 13, color: colors.brand },
  fence: { backgroundColor: '#F2F2F7', borderRadius: 6, padding: 8, fontFamily: 'Menlo', fontSize: 12, marginVertical: 4 },
  paragraph: { marginVertical: 2 },
  link: { color: colors.brand },
});

export const mdStylesCompact = StyleSheet.create({
  body: { fontSize: 14, lineHeight: 20, color: colors.labelPrimary },
  heading2: { fontSize: 15, fontWeight: '700', color: colors.labelPrimary, marginTop: 4, marginBottom: 2 },
  heading3: { fontSize: 14, fontWeight: '600', color: colors.labelPrimary, marginTop: 3 },
  strong: { fontWeight: '600' },
  bullet_list: { marginVertical: 2 },
  list_item: { flexDirection: 'row', marginVertical: 1 },
  code_inline: { backgroundColor: '#F2F2F7', borderRadius: 4, paddingHorizontal: 3, fontFamily: 'Menlo', fontSize: 12, color: colors.brand },
  fence: { backgroundColor: '#F2F2F7', borderRadius: 6, padding: 8, fontFamily: 'Menlo', fontSize: 12, marginVertical: 4 },
  paragraph: { marginVertical: 2 },
  link: { color: colors.brand },
});
