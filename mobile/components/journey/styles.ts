import { StyleSheet } from 'react-native';
import { revaColors as C, revaRadii as R, revaSemantic } from '../../constants/revaTheme';
export const journeyStyles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.paper },
  content: { padding: 20, gap: 16, paddingBottom: 60 },
  row: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 12 },
  between: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  heading: { fontSize: 22, fontWeight: '700', color: C.ink1 },
  body: { fontSize: 15, lineHeight: 23, color: C.ink1 },
  note: { fontSize: 12, lineHeight: 19, color: C.ink2 },
  label: { fontSize: 13, fontWeight: '600', color: C.ink2 },
  card: { backgroundColor: C.surface, borderRadius: R.lg, padding: 18, gap: 12, borderWidth: 1, borderColor: C.line },
  input: { backgroundColor: C.paper2, padding: 14, borderRadius: R.md, color: C.ink1, fontSize: 16 },
  button: { backgroundColor: C.green500, paddingHorizontal: 18, paddingVertical: 14, borderRadius: R.pill, alignItems: 'center' },
  buttonText: { color: C.greenOn, fontWeight: '600', fontSize: 14 },
  secondary: { paddingHorizontal: 14, paddingVertical: 12, backgroundColor: C.green50, borderRadius: R.pill },
  link: { color: C.green600, fontSize: 14, fontWeight: '600' },
  error: { color: revaSemantic.risk.fg, fontSize: 13, lineHeight: 20 },
  disabled: { opacity: 0.45 },
  selected: { borderWidth: 2, borderColor: C.green500 },
});
