import React, { createContext, useContext, useState, useCallback, useRef } from 'react';
import { View, Text, StyleSheet, Animated, TextStyle } from 'react-native';
import { colors, radii, shadows } from '@/constants/theme';

interface ToastCtx {
  show: (msg: string, type?: 'info' | 'error' | 'success') => void;
}

const ToastContext = createContext<ToastCtx>({ show: () => {} });

export function useToast() { return useContext(ToastContext); }

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [msg, setMsg] = useState('');
  const [type, setType] = useState<'info' | 'error' | 'success'>('info');
  const translateY = useRef(new Animated.Value(-80)).current;
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const show = useCallback((message: string, t: 'info' | 'error' | 'success' = 'info') => {
    setMsg(message);
    setType(t);
    if (timerRef.current) clearTimeout(timerRef.current);
    Animated.spring(translateY, { toValue: 60, useNativeDriver: true, friction: 10 }).start();
    timerRef.current = setTimeout(() => {
      Animated.timing(translateY, { toValue: -80, duration: 250, useNativeDriver: true }).start();
    }, 3000);
  }, []);

  const bg = type === 'error' ? '#FF453A' : type === 'success' ? '#30D158' : '#1C1C1E';

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <Animated.View style={[styles.toast, { backgroundColor: bg, transform: [{ translateY }] }]} pointerEvents="none">
        <Text style={txt.toastText}>{msg}</Text>
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
});

const txt = {
  toastText: { fontSize: 14, color: '#fff', textAlign: 'center', fontWeight: '500' } as TextStyle,
};
