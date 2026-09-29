import React, { useEffect, useState } from 'react';
import { Modal, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { FAMILY_RELATIONSHIPS, type FamilyMember } from '../../services/family';
import type { ColorPalette } from '../../hooks/useTheme';
import { radii, spacing } from '../../constants/theme';

interface Props {
  visible: boolean;
  c: ColorPalette;
  mode: 'accept' | 'edit';
  member?: FamilyMember | null;
  onClose: () => void;
  onSubmit: (relationship: string, nickname: string, code?: string) => Promise<void>;
}

export default function FamilyRelationshipForm({ visible, c, mode, member, onClose, onSubmit }: Props) {
  const [code, setCode] = useState('');
  const [relationship, setRelationship] = useState('other');
  const [nickname, setNickname] = useState('');
  const [consented, setConsented] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!visible) return;
    setCode('');
    setRelationship(member?.relationship_type || 'other');
    setNickname(member?.nickname || '');
    setConsented(false);
    setError('');
  }, [visible, member]);
  const enabled = !pending && (mode === 'edit' || (consented && /^[A-Z0-9]{6}$/.test(code.trim().toUpperCase())));
  const submit = async () => {
    if (!enabled) return;
    setPending(true);
    setError('');
    try {
      await onSubmit(relationship, nickname.trim(), mode === 'accept' ? code.trim().toUpperCase() : undefined);
    } catch (cause) {
      const failure = cause as { response?: { data?: { detail?: unknown } }; message?: string };
      const detail = failure.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : failure.message || '保存失败，请稍后重试');
    } finally {
      setPending(false);
    }
  };
  const styles = StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    content: { padding: spacing.lg, gap: spacing.md },
    title: { fontSize: 20, fontWeight: '600', color: c.labelPrimary },
    text: { fontSize: 14, lineHeight: 22, color: c.labelPrimary },
    hint: { fontSize: 13, lineHeight: 21, color: c.labelSecondary },
    input: { padding: spacing.md, backgroundColor: c.fill, borderRadius: radii.sm, color: c.labelPrimary },
    choices: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    choice: { padding: spacing.sm, borderRadius: radii.sm, borderWidth: 1, borderColor: c.separator },
    button: { padding: spacing.md, alignItems: 'center', borderRadius: radii.sm },
  });
  return <Modal visible={visible} animationType="slide" onRequestClose={() => { if (!pending) onClose(); }}>
    <SafeAreaProvider>
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
        <Text style={styles.title}>{mode === 'accept' ? '加入家庭健康' : '设置关系与昵称'}</Text>
        {mode === 'accept' && <>
          <Text style={styles.text}>请输入家人给你的 6 位邀请码</Text>
          <TextInput accessibilityLabel="邀请码" autoCapitalize="characters" autoCorrect={false} maxLength={12} value={code} onChangeText={setCode} editable={!pending} style={styles.input} />
        </>}
        {mode === 'edit' && <Text style={styles.text}>{member?.name || member?.nickname || '家人'}</Text>}
        <Text style={styles.text}>{mode === 'accept' ? '我是家庭创建者的' : '这位家人是我的'}</Text>
        <View style={styles.choices}>
          {Object.entries(FAMILY_RELATIONSHIPS).filter(([key]) => key !== 'self').map(([key, label]) => <TouchableOpacity key={key} accessibilityRole="radio" accessibilityState={{ selected: relationship === key }} disabled={pending} onPress={() => setRelationship(key)} style={[styles.choice, relationship === key && { borderColor: c.brand, backgroundColor: c.brandLight }]}>
            <Text style={styles.text}>{label}</Text>
          </TouchableOpacity>)}
        </View>
        <Text style={styles.text}>家庭昵称（可选）</Text>
        <TextInput accessibilityLabel="家庭昵称" maxLength={50} value={nickname} onChangeText={setNickname} editable={!pending} style={styles.input} />
        {mode === 'accept' ? <TouchableOpacity accessibilityRole="checkbox" accessibilityLabel="同意向家庭创建者共享健康记录" accessibilityState={{ checked: consented }} disabled={pending} onPress={() => setConsented(!consented)}>
          <Text style={styles.text}>{consented ? '☑' : '□'} 我同意让家庭创建者查看我的健康概况、检查报告和病程记录。此授权仅供查看，不允许修改我的记录或用药。</Text>
          <Text style={styles.hint}>请使用本人账号加入；未成年人的账号由监护人协助确认。可在家庭健康页退出家庭，停止共享。</Text>
        </TouchableOpacity> : <Text style={styles.hint}>修改称谓和昵称不会扩大健康数据共享权限。</Text>}
        {!!error && <Text accessibilityRole="alert" style={{ color: c.red }}>{error}</Text>}
        <TouchableOpacity accessibilityRole="button" disabled={!enabled} onPress={() => { void submit(); }} style={[styles.button, { backgroundColor: c.brandLight, opacity: enabled ? 1 : 0.5 }]}>
          <Text style={{ color: c.brand }}>{pending ? '正在保存…' : mode === 'accept' ? '同意并加入' : '保存关系'}</Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="button" disabled={pending} onPress={onClose} style={styles.button}><Text style={styles.hint}>取消</Text></TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
    </SafeAreaProvider>
  </Modal>;
}
