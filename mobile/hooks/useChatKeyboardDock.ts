import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppState, Dimensions, Keyboard, Platform } from 'react-native';

interface ChatKeyboardDockOptions {
  bottomInset: number;
  restingSpace: number;
  onKeyboardShown?: () => void;
}

export function useChatKeyboardDock({ bottomInset, restingSpace, onKeyboardShown }: ChatKeyboardDockOptions) {
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [keyboardHeight, setKeyboardHeight] = useState(0);

  const applyKeyboardFrame = useCallback((event: any) => {
    const end = event?.endCoordinates;
    if (!end) return;
    const windowH = Dimensions.get('window').height;
    const height = typeof end.screenY === 'number'
      ? Math.max(0, Math.round(windowH - end.screenY))
      : Math.max(0, Math.round(end.height || 0));
    setKeyboardVisible(height > 0);
    setKeyboardHeight(height);
  }, []);

  const clearKeyboardFrame = useCallback(() => {
    setKeyboardVisible(false);
    setKeyboardHeight(0);
  }, []);

  const syncKeyboardMetrics = useCallback(() => {
    const metrics = typeof (Keyboard as any).metrics === 'function'
      ? (Keyboard as any).metrics()
      : undefined;
    if (metrics) {
      applyKeyboardFrame({ endCoordinates: metrics });
    } else {
      clearKeyboardFrame();
    }
  }, [applyKeyboardFrame, clearKeyboardFrame]);

  useEffect(() => {
    const subs = [
      Keyboard.addListener('keyboardDidShow', (event) => {
        applyKeyboardFrame(event);
        onKeyboardShown?.();
      }),
      Keyboard.addListener('keyboardWillChangeFrame', applyKeyboardFrame),
      Keyboard.addListener('keyboardDidChangeFrame', applyKeyboardFrame),
      Keyboard.addListener('keyboardDidHide', clearKeyboardFrame),
      AppState.addEventListener('change', (state) => {
        if (state === 'active') {
          syncKeyboardMetrics();
        } else {
          clearKeyboardFrame();
        }
      }),
    ];
    return () => {
      subs.forEach(sub => sub.remove());
    };
  }, [applyKeyboardFrame, clearKeyboardFrame, onKeyboardShown, syncKeyboardMetrics]);

  return useMemo(() => {
    const keyboardSpacerHeight = Platform.OS === 'ios' && keyboardVisible ? keyboardHeight : 0;
    return {
      keyboardVisible,
      keyboardHeight,
      bottomSpacerHeight: keyboardVisible ? keyboardSpacerHeight : bottomInset + restingSpace,
    };
  }, [bottomInset, keyboardHeight, keyboardVisible, restingSpace]);
}
