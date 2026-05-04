import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import { View, Text, StyleSheet, Animated, TextStyle, Pressable } from 'react-native';
import { colors, radii, shadows, spacing } from '../constants/theme';

interface ToastCtx {
  show: (msg: string, type?: 'info' | 'error' | 'success') => void;
  /**
   * 显示带"撤销"按钮的 toast.
   * P8 (2026-05-04): 用于 ActionCard 完成等不可逆动作的反悔窗口.
   * onUndo 被调用时 toast 立刻消失.
   */
  showUndoable: (msg: string, onUndo: () => void | Promise<void>, durationMs?: number) => void;
}

const ToastContext = createContext<ToastCtx>({
  show: () => {},
  showUndoable: () => {},
});

export function useToast() { return useContext(ToastContext); }

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [msg, setMsg] = useState('');
  const [type, setType] = useState<'info' | 'error' | 'success'>('info');
  const [undoCallback, setUndoCallback] = useState<(() => void | Promise<void>) | null>(null);
  const translateY = useRef(new Animated.Value(-80)).current;
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const dismiss = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    Animated.timing(translateY, { toValue: -80, duration: 250, useNativeDriver: true }).start();
    setUndoCallback(null);
  }, []);

  const show = useCallback((message: string, t: 'info' | 'error' | 'success' = 'info') => {
    setMsg(message);
    setType(t);
    setUndoCallback(null);
    if (timerRef.current) clearTimeout(timerRef.current);
    Animated.spring(translateY, { toValue: 60, useNativeDriver: true, friction: 10 }).start();
    timerRef.current = setTimeout(() => {
      Animated.timing(translateY, { toValue: -80, duration: 250, useNativeDriver: true }).start();
    }, 3000);
  }, []);

  const showUndoable = useCallback((
    message: string,
    onUndo: () => void | Promise<void>,
    durationMs: number = 5000,
  ) => {
    setMsg(message);
    setType('success');
    // 用 wrapper 函数把当前 onUndo 存进 state, React state 不接受函数本身
    setUndoCallback(() => onUndo);
    if (timerRef.current) clearTimeout(timerRef.current);
    Animated.spring(translateY, { toValue: 60, useNativeDriver: true, friction: 10 }).start();
    timerRef.current = setTimeout(() => {
      Animated.timing(translateY, { toValue: -80, duration: 250, useNativeDriver: true }).start();
      setUndoCallback(null);
    }, durationMs);
  }, []);

  const handleUndoPress = useCallback(() => {
    if (!undoCallback) return;
    try {
      const r = undoCallback();
      if (r && typeof (r as Promise<void>).then === 'function') {
        (r as Promise<void>).catch(() => { /* swallow */ });
      }
    } catch { /* swallow */ }
    dismiss();
  }, [undoCallback, dismiss]);

  const bg = type === 'error' ? '#FF453A' : type === 'success' ? '#30D158' : '#1C1C1E';

  return (
    <ToastContext.Provider value={{ show, showUndoable }}>
      {children}
      <Animated.View
        style={[styles.toast, { backgroundColor: bg, transform: [{ translateY }] }]}
        pointerEvents={undoCallback ? 'box-none' : 'none'}
      >
        <View style={styles.row}>
          <Text style={txt.toastText} numberOfLines={2}>{msg}</Text>
          {undoCallback ? (
            <Pressable
              onPress={handleUndoPress}
              hitSlop={6}
              style={({ pressed }) => [styles.undoBtn, pressed && { opacity: 0.6 }]}
              accessibilityRole="button"
              accessibilityLabel="撤销"
            >
              <Text style={txt.undoText}>撤销</Text>
            </Pressable>
          ) : null}
        </View>
      </Animated.View>
    </ToastContext.Provider>
  );
}

const styles = StyleSheet.create({
  toast: {
    position: 'absolute', top: 0, left: 20, right: 20,
    borderRadius: radii.md, paddingHorizontal: 16, paddingVertical: 12,
    ...shadows.heavy, zIndex: 9999,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  undoBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    borderRadius: radii.full,
    backgroundColor: 'rgba(255,255,255,0.18)',
  },
});

const txt = {
  toastText: {
    flex: 1,
    fontSize: 14, color: '#fff', textAlign: 'left', fontWeight: '500',
  } as TextStyle,
  undoText: { fontSize: 13, color: '#fff', fontWeight: '700' } as TextStyle,
};
