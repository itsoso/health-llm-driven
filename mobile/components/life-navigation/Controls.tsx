import React from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { useTheme } from '../../hooks/useTheme';
export function useLifeControls(disabled = false) {
    const { c } = useTheme();
    const text = (value: string) => <Text style={{ fontSize: 13, lineHeight: 18, color: c.labelPrimary }}>{value}</Text>;
    const button = (label: string, run: () => void, off = false) => <Pressable key={label} accessibilityRole="button" accessibilityLabel={label} disabled={disabled || off} onPress={run} style={{ paddingHorizontal: 10, paddingVertical: 6, minHeight: 44, justifyContent: 'center', borderWidth: 1, borderColor: c.separator, borderRadius: 10, opacity: disabled || off ? .5 : 1 }}><Text style={{ fontSize: 13, lineHeight: 18, color: c.brand }}>{label}</Text></Pressable>;
    const field = (label: string, value: string, change: (v: string) => void, numeric = false, maxLength = 4000) => <View key={label} style={{ gap: 4 }}>{text(label)}<TextInput accessibilityLabel={label} value={value} onChangeText={change} editable={!disabled} multiline={!numeric} keyboardType={numeric ? 'number-pad' : 'default'} maxLength={maxLength} style={{ fontSize: 13, lineHeight: 18, padding: 8, borderWidth: 1, borderColor: c.separator, borderRadius: 10, color: c.labelPrimary, minHeight: 44 }}/></View>;
    return { c, text, button, field };
}
