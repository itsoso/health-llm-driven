/**
 * 「我的配方」管理 sheet(Harness Slice 3)— 从聊天页 ⋯ 菜单进入。
 * v1:列表 + 删除。执行入口是对话本身(对小巴精确说出触发短语)。
 * 加载失败显式呈现 + 重试;删除失败如实报错,不静默吞。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  deleteRecipe,
  listRecipes,
  type ProcedureRecipe,
} from '../../services/procedureRecipes';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaSpacing,
} from '../../constants/revaTheme';

function RecipeRow({
  recipe,
  onDelete,
  deleting,
}: {
  recipe: ProcedureRecipe;
  onDelete: (recipe: ProcedureRecipe) => void;
  deleting: boolean;
}) {
  const phrases = (recipe.trigger_phrases || []).join('」「');
  return (
    <View style={styles.row} accessibilityLabel={`配方:${recipe.name}`}>
      <View style={styles.rowMain}>
        <Text maxFontSizeMultiplier={1.2} style={txt.rowTitle} numberOfLines={1}>
          {recipe.name}
        </Text>
        <Text maxFontSizeMultiplier={1.2} style={txt.rowMeta} numberOfLines={2}>
          说「{phrases}」触发 · {recipe.steps?.length ?? 0} 步 · 已用 {recipe.use_count} 次
        </Text>
      </View>
      <TouchableOpacity
        onPress={() => onDelete(recipe)}
        disabled={deleting}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel={`删除配方 ${recipe.name}`}
      >
        {deleting ? (
          <ActivityIndicator size="small" color={revaSemantic.risk.fg} />
        ) : (
          <Ionicons name="trash-outline" size={17} color={revaSemantic.risk.fg} />
        )}
      </TouchableOpacity>
    </View>
  );
}

export default function RecipeManagerSheet({
  visible,
  onClose,
}: {
  visible: boolean;
  onClose: () => void;
}) {
  const [recipes, setRecipes] = useState<ProcedureRecipe[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRecipes(await listRecipes());
    } catch {
      setError('配方列表加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (visible) void load();
  }, [visible, load]);

  const confirmDelete = useCallback((recipe: ProcedureRecipe) => {
    Alert.alert(
      '删除配方',
      `删除「${recipe.name}」后，说「${(recipe.trigger_phrases || [])[0] ?? ''}」将不再触发重放。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            setDeletingId(recipe.id);
            try {
              await deleteRecipe(recipe.id);
              setRecipes((prev) => (prev ?? []).filter((r) => r.id !== recipe.id));
            } catch {
              setError('删除失败，请稍后重试');
            } finally {
              setDeletingId(null);
            }
          },
        },
      ],
    );
  }, []);

  const empty = !loading && !error && (recipes?.length ?? 0) === 0;

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.overlay} onPress={onClose}>
        {/* onPress no-op: 吞掉 sheet 内点击, 不让它冒泡到 overlay 关闭 sheet */}
        <Pressable style={styles.sheet} testID="recipe-manager-sheet" onPress={() => {}}>
          <View style={styles.header}>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text maxFontSizeMultiplier={1.2} style={txt.headerTitle}>我的配方</Text>
              <Text maxFontSizeMultiplier={1.2} style={txt.headerSub}>
                对小巴精确说出触发短语即可一键重放；敏感步骤仍需确认
              </Text>
            </View>
            <TouchableOpacity
              onPress={onClose}
              hitSlop={10}
              accessibilityRole="button"
              accessibilityLabel="关闭配方管理"
            >
              <Ionicons name="close" size={22} color={C.ink2} />
            </TouchableOpacity>
          </View>

          {loading ? (
            <View style={styles.centerBox} accessibilityLabel="正在加载配方列表">
              <ActivityIndicator size="small" color={C.green500} />
            </View>
          ) : error ? (
            <View style={styles.centerBox}>
              <Text maxFontSizeMultiplier={1.2} style={txt.error}>{error}</Text>
              <TouchableOpacity
                onPress={load}
                style={styles.retryButton}
                accessibilityRole="button"
                accessibilityLabel="重试加载配方列表"
              >
                <Text maxFontSizeMultiplier={1.2} style={txt.retry}>重试</Text>
              </TouchableOpacity>
            </View>
          ) : empty ? (
            <View style={styles.centerBox}>
              <Ionicons name="bookmark-outline" size={22} color={C.ink3} />
              <Text maxFontSizeMultiplier={1.2} style={txt.empty}>
                还没有配方。一轮对话里完成多条记录后，结果卡上会出现「存为配方」。
              </Text>
            </View>
          ) : (
            <ScrollView contentContainerStyle={styles.listContent}>
              {(recipes ?? []).map((recipe) => (
                <RecipeRow
                  key={recipe.id}
                  recipe={recipe}
                  onDelete={confirmDelete}
                  deleting={deletingId === recipe.id}
                />
              ))}
            </ScrollView>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 20, 0.45)',
    justifyContent: 'flex-end',
  },
  sheet: {
    maxHeight: '72%',
    minHeight: 260,
    backgroundColor: C.surface,
    borderTopLeftRadius: revaRadii.lg,
    borderTopRightRadius: revaRadii.lg,
    padding: revaSpacing.s4,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    marginBottom: revaSpacing.s2,
  },
  centerBox: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: revaSpacing.s6,
    paddingHorizontal: revaSpacing.s4,
  },
  retryButton: {
    marginTop: 4,
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
  },
  listContent: {
    gap: 8,
    paddingBottom: revaSpacing.s6,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: revaRadii.md,
    backgroundColor: C.paper,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  rowMain: {
    flex: 1,
    minWidth: 0,
    gap: 2,
  },
});

const txt = {
  headerTitle: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '800', color: C.ink1 } as TextStyle,
  headerSub: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3, marginTop: 1 } as TextStyle,
  rowTitle: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', color: C.ink1 } as TextStyle,
  rowMeta: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3 } as TextStyle,
  empty: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink3, textAlign: 'center', lineHeight: 19 } as TextStyle,
  error: { fontFamily: revaFonts.sans, fontSize: 14, color: revaSemantic.risk.fg } as TextStyle,
  retry: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.green600 } as TextStyle,
};
