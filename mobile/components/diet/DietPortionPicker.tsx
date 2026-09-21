import React from 'react';
import { View, Text, TextInput, Pressable, StyleSheet } from 'react-native';
import { revaColors as C, revaRadii, revaSemantic } from '../../constants/revaTheme';
import { parseDietPortion } from '../../utils/dietPortion';
import { formatDisplayNumber } from '../../utils/displayNumber';

export function DietPortionPicker({ value, onChange, disabled = false }: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  const fraction = parseDietPortion(value);
  return (
    <View style={styles.container}>
      <Text style={styles.title}>我吃的份额</Text>
      <Text style={styles.hint}>聚餐填整桌菜，再选自己吃的比例；各菜吃得不均匀时，请改具体菜量。</Text>
      <View style={styles.row}>
        {['1', '1/2', '1/3', '1/4', '1/5'].map(token => {
          const selected = fraction === parseDietPortion(token);
          return <Pressable key={token} accessibilityRole="button"
            accessibilityLabel={`我吃了 ${token === '1' ? '整份' : token}`}
            accessibilityState={{ selected, disabled }} disabled={disabled}
            onPress={() => onChange(token)} style={[styles.chip, selected && styles.selected]}>
            <Text style={[styles.chipText, selected && styles.selectedText]}>{token === '1' ? '整份' : token}</Text>
          </Pressable>;
        })}
      </View>
      <View style={styles.customRow}>
        <Text style={styles.hint}>自定义</Text>
        <TextInput accessibilityLabel="自定义食用份额" placeholder="例如 1/5 或 20%"
          value={value} onChangeText={onChange} editable={!disabled} autoCorrect={false}
          maxLength={24} style={styles.input} />
      </View>
      <Text accessibilityLiveRegion="polite" style={[styles.hint, fraction === null && styles.error]}>
        {fraction === null ? '请输入大于 0、不超过 100% 的份额，例如 1/5。'
          : fraction === 1 ? '按描述的整份计入个人饮食。'
          : `仅按整桌的 ${formatDisplayNumber(fraction * 100)}% 计入个人饮食；热量及营养按比例估算。`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 8, marginVertical: 10 },
  title: { fontSize: 14, fontWeight: '600', color: C.ink1 },
  hint: { fontSize: 12, color: C.ink3, lineHeight: 18 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { borderRadius: revaRadii.lg, backgroundColor: C.paper2, paddingHorizontal: 14, minHeight: 44, justifyContent: 'center' },
  selected: { backgroundColor: C.green600 },
  chipText: { fontSize: 14, color: C.ink1 },
  selectedText: { color: '#fff', fontWeight: '600' },
  customRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  input: { flex: 1, minHeight: 44, paddingHorizontal: 12, borderRadius: revaRadii.md, backgroundColor: C.paper2, color: C.ink1 },
  error: { color: revaSemantic.risk.fg },
});
