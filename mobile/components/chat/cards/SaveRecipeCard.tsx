/**
 * 「存为配方」卡(Harness Slice 3)— 后端在一轮完成 ≥2 个写类工具后,
 * done.cards 下发 save_recipe 描述符;这张卡渲染入口 + 命名/触发短语 sheet。
 *
 * 协议: { type: "save_recipe", data: { conversation_id, step_count, steps_preview[] } }
 *
 * 安全边界(与后端一致,卡上如实告知):
 * - 配方是确定性重放的工具序列,触发短语**精确匹配**才执行;
 * - 用药等敏感步骤重放时仍会要求确认,不因存成配方而免确认。
 */
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaSpacing,
} from '../../../constants/revaTheme';
import { saveRecipeFromConversation } from '../../../services/procedureRecipes';
import type { CardSpec } from './types';

export interface SaveRecipeCardData {
  conversation_id: number;
  step_count: number;
  steps_preview?: string[];
}

export function SaveRecipeCardView(data: SaveRecipeCardData) {
  const [sheetVisible, setSheetVisible] = useState(false);
  const [name, setName] = useState('');
  const [phrase, setPhrase] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedName, setSavedName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const previews = Array.isArray(data.steps_preview) ? data.steps_preview.slice(0, 5) : [];
  const canSubmit = name.trim().length > 0 && phrase.trim().length >= 2 && !saving;

  const submit = async () => {
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      const recipe = await saveRecipeFromConversation(data.conversation_id, {
        name: name.trim(),
        trigger_phrases: [phrase.trim()],
      });
      setSavedName(recipe.name);
      setSheetVisible(false);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : '保存失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <CardShell icon="bookmark-outline" iconColor={C.green600} title="存为配方" badge={`${data.step_count} 步`}>
      {previews.length > 0 ? (
        <Text maxFontSizeMultiplier={1.2} style={txt.preview} numberOfLines={2}>
          {previews.join(' → ')}
        </Text>
      ) : null}
      {savedName ? (
        <View style={styles.savedRow} testID="save-recipe-saved">
          <Ionicons name="checkmark-circle" size={14} color={C.green600} />
          <Text maxFontSizeMultiplier={1.2} style={txt.saved}>
            已存为「{savedName}」，对我说触发短语即可一键重放
          </Text>
        </View>
      ) : (
        <Pressable
          style={({ pressed }) => [styles.openButton, pressed && { opacity: 0.85 }]}
          accessibilityRole="button"
          accessibilityLabel="存为配方"
          onPress={() => setSheetVisible(true)}
        >
          <Ionicons name="add-circle-outline" size={14} color={C.green600} />
          <Text maxFontSizeMultiplier={1.2} style={txt.openButton}>存为配方</Text>
        </Pressable>
      )}

      <Modal
        visible={sheetVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setSheetVisible(false)}
      >
        <Pressable style={styles.overlay} onPress={() => setSheetVisible(false)}>
          {/* onPress no-op: 吞掉 sheet 内点击, 不让它冒泡到 overlay 关闭 sheet */}
          <Pressable style={styles.sheet} testID="save-recipe-sheet" onPress={() => {}}>
            <View style={styles.sheetHeader}>
              <Text maxFontSizeMultiplier={1.2} style={txt.sheetTitle}>存为配方</Text>
              <Pressable
                onPress={() => setSheetVisible(false)}
                hitSlop={8}
                accessibilityRole="button"
                accessibilityLabel="关闭存配方"
              >
                <Ionicons name="close" size={20} color={C.ink2} />
              </Pressable>
            </View>
            <Text maxFontSizeMultiplier={1.2} style={txt.sheetSub}>
              把这轮 {data.step_count} 步记录存成可重放的固定流程
            </Text>

            <Text maxFontSizeMultiplier={1.2} style={txt.label}>配方名称</Text>
            <TextInput
              style={styles.input}
              value={name}
              onChangeText={setName}
              placeholder="如：早餐套餐"
              placeholderTextColor={C.ink3}
              maxLength={40}
              accessibilityLabel="配方名称"
            />

            <Text maxFontSizeMultiplier={1.2} style={txt.label}>触发短语（需精确说出才执行）</Text>
            <TextInput
              style={styles.input}
              value={phrase}
              onChangeText={setPhrase}
              placeholder="如：早餐套餐打卡"
              placeholderTextColor={C.ink3}
              maxLength={40}
              accessibilityLabel="触发短语"
            />
            <Text maxFontSizeMultiplier={1.2} style={txt.hint}>
              重放时用药等敏感步骤仍会逐条要你确认，不会因配方跳过。
            </Text>

            {error ? (
              <Text maxFontSizeMultiplier={1.2} style={txt.error} testID="save-recipe-error">
                {error}
              </Text>
            ) : null}

            <Pressable
              style={({ pressed }) => [
                styles.submitButton,
                !canSubmit && styles.submitButtonDisabled,
                pressed && canSubmit && { opacity: 0.85 },
              ]}
              disabled={!canSubmit}
              accessibilityRole="button"
              accessibilityLabel="确认保存配方"
              onPress={submit}
            >
              {saving ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Text maxFontSizeMultiplier={1.2} style={txt.submit}>保存配方</Text>
              )}
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </CardShell>
  );
}

export const SaveRecipeCardSpec: CardSpec<SaveRecipeCardData> = {
  type: 'save_recipe',
  label: '存为配方',
  // 只接受后端下发, 不做本地关键词触发
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <SaveRecipeCardView {...data} />,
};

const styles = StyleSheet.create({
  savedRow: {
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  openButton: {
    marginTop: 8,
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 20, 0.45)',
    justifyContent: 'center',
    paddingHorizontal: revaSpacing.s4,
  },
  sheet: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    padding: revaSpacing.s4,
    gap: 6,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    borderRadius: revaRadii.md,
    paddingHorizontal: 12,
    paddingVertical: 9,
    fontFamily: revaFonts.sans,
    fontSize: 14,
    color: C.ink1,
    backgroundColor: C.paper,
  },
  submitButton: {
    marginTop: 10,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 11,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green600,
  },
  submitButtonDisabled: {
    opacity: 0.45,
  },
});

const txt = {
  preview: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, marginTop: 4 } as TextStyle,
  saved: { fontFamily: revaFonts.sans, fontSize: 12, color: C.green600, flex: 1 } as TextStyle,
  openButton: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.green600 } as TextStyle,
  sheetTitle: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '800', color: C.ink1 } as TextStyle,
  sheetSub: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginBottom: 4 } as TextStyle,
  label: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '700', color: C.ink2, marginTop: 6 } as TextStyle,
  hint: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, marginTop: 4 } as TextStyle,
  error: { fontFamily: revaFonts.sans, fontSize: 12, color: revaSemantic.risk.fg, marginTop: 6 } as TextStyle,
  submit: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '700', color: '#fff' } as TextStyle,
};
