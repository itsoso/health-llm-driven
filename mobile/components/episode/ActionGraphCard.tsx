/**
 * ActionGraphCard — Episode 详情里的单个 Action 卡片.
 *
 * 视觉:
 *   左侧 icon (status 决定色) + 标题 + body + 时间窗 + 状态 chip + 完成/跳过按钮
 *   pending: 主色, 高亮
 *   done:    绿勾, 静音
 *   skipped: 灰
 *   expired: 灰 + 删除线
 *
 * 完成动作走 Haptic.Success, 跳过走 Selection.
 */
import React, { useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { spacing, radii, shadows } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { EpisodeAction, ActionStatus } from '../../services/episodes';

interface Props {
  action: EpisodeAction;
  onDone: (actionId: number) => void;
  onSkip: (actionId: number) => void;
  pending?: boolean;
}

export default function ActionGraphCard({ action, onDone, onSkip, pending }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c, action.status), [c, action.status]);

  const iconName = (action.icon as any) || _defaultIcon(action.action_type);
  const isInteractive = action.status === 'pending';

  const handleDone = () => {
    if (!isInteractive || pending) return;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    onDone(action.id);
  };
  const handleSkip = () => {
    if (!isInteractive || pending) return;
    Haptics.selectionAsync();
    onSkip(action.id);
  };

  const window = _formatWindow(action.time_window_start, action.time_window_end);

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <View style={styles.iconWrap}>
          <Ionicons name={iconName as any} size={22} color={_iconColor(c, action.status)} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.title} numberOfLines={3}>{action.title}</Text>
          {!!action.body && (
            <Text style={styles.body} numberOfLines={6}>{action.body}</Text>
          )}
          {!!window && (
            <Text style={styles.window}>{window}</Text>
          )}
        </View>
        <StatusPill status={action.status} c={c} />
      </View>

      {isInteractive && (
        <View style={styles.actionsRow}>
          <TouchableOpacity
            onPress={handleSkip}
            disabled={pending}
            style={[styles.btnGhost, pending && styles.btnDisabled]}
          >
            <Text style={styles.btnGhostText}>跳过</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={handleDone}
            disabled={pending}
            style={[styles.btnPrimary, pending && styles.btnDisabled]}
          >
            {pending ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <>
                <Ionicons name="checkmark" size={18} color="#fff" />
                <Text style={styles.btnPrimaryText}>完成</Text>
              </>
            )}
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

function StatusPill({ status, c }: { status: ActionStatus; c: ColorPalette }) {
  const map: Record<ActionStatus, { label: string; color: string; bg: string }> = {
    pending: { label: '待办', color: c.brand, bg: c.brandLight },
    done: { label: '已完成', color: c.green, bg: 'rgba(48,209,88,0.12)' },
    skipped: { label: '已跳过', color: c.labelTertiary, bg: 'rgba(174,174,178,0.18)' },
    expired: { label: '已过期', color: c.labelTertiary, bg: 'rgba(174,174,178,0.18)' },
  };
  const s = map[status];
  return (
    <View style={{
      paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999,
      backgroundColor: s.bg, alignSelf: 'flex-start',
    }}>
      <Text style={{ fontSize: 11, fontWeight: '600', color: s.color }}>{s.label}</Text>
    </View>
  );
}

function _iconColor(c: ColorPalette, status: ActionStatus): string {
  if (status === 'done') return c.green;
  if (status === 'skipped' || status === 'expired') return c.labelTertiary;
  return c.brand;
}

function _defaultIcon(actionType: string): string {
  if (actionType.includes('rehydrate') || actionType.includes('water')) return 'water-outline';
  if (actionType.includes('protein') || actionType.includes('fuel')) return 'restaurant-outline';
  if (actionType.includes('sleep') || actionType.includes('bedtime')) return 'bed-outline';
  if (actionType.includes('cool')) return 'snow-outline';
  if (actionType.includes('check_in') || actionType.includes('checkin')) return 'chatbubble-ellipses-outline';
  if (actionType.includes('emergency')) return 'alert-circle-outline';
  if (actionType.includes('rest')) return 'moon-outline';
  if (actionType.includes('demote') || actionType.includes('skip')) return 'remove-circle-outline';
  if (actionType.includes('record')) return 'document-text-outline';
  return 'fitness-outline';
}

function _formatWindow(start: string | null, end: string | null): string {
  if (!start && !end) return '';
  const fmt = (iso: string) => {
    try {
      const d = new Date(iso);
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      return `${hh}:${mm}`;
    } catch { return ''; }
  };
  if (start && end) return `时间窗 ${fmt(start)} – ${fmt(end)}`;
  return start ? `从 ${fmt(start)} 开始` : `截止 ${fmt(end!)}`;
}

const createStyles = (c: ColorPalette, status: ActionStatus) =>
  StyleSheet.create({
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.lg,
      marginBottom: spacing.md,
      borderWidth: 1,
      borderColor: status === 'pending' ? c.separator : 'transparent',
      ...shadows.subtle,
      opacity: status === 'expired' ? 0.55 : 1,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: spacing.md,
    },
    iconWrap: {
      width: 38, height: 38, borderRadius: radii.md,
      alignItems: 'center', justifyContent: 'center',
      backgroundColor: c.brandLight,
    },
    title: {
      fontSize: 16, fontWeight: '600', color: c.labelPrimary,
      lineHeight: 22,
      textDecorationLine: status === 'expired' ? 'line-through' : 'none',
    },
    body: {
      fontSize: 14, color: c.labelSecondary, marginTop: 4, lineHeight: 20,
    },
    window: {
      marginTop: 6, fontSize: 12, color: c.labelTertiary, fontWeight: '500',
    },
    actionsRow: {
      flexDirection: 'row',
      gap: spacing.sm,
      marginTop: spacing.md,
      justifyContent: 'flex-end',
    },
    btnPrimary: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      backgroundColor: c.brand,
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      borderRadius: radii.full,
      minWidth: 92,
      justifyContent: 'center',
    },
    btnPrimaryText: { color: '#fff', fontSize: 14, fontWeight: '600' },
    btnGhost: {
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      borderRadius: radii.full,
      borderWidth: 1,
      borderColor: c.separator,
    },
    btnGhostText: { color: c.labelSecondary, fontSize: 14, fontWeight: '500' },
    btnDisabled: { opacity: 0.5 },
  });
