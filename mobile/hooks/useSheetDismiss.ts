import { useEffect, useMemo, useRef } from 'react';
import { Animated, PanResponder } from 'react-native';

export function useSheetDismiss(onDismiss: () => void, visible: boolean) {
  const translateY = useRef(new Animated.Value(0)).current;
  const dismissRef = useRef(onDismiss);
  dismissRef.current = onDismiss;
  useEffect(() => {
    translateY.stopAnimation();
    translateY.setValue(0);
  }, [translateY, visible]);
  // Attach only to the header: list scrolling, inputs and image gestures keep ownership.
  const responder = useMemo(() => PanResponder.create({
    // Bubble only: close buttons retain their own responder; the inert header
    // accepts touch start so Fabric tracks the whole drag, including short headers.
    onStartShouldSetPanResponder: event => event.nativeEvent.touches.length === 1,
    onMoveShouldSetPanResponder: (_, gesture) => gesture.numberActiveTouches === 1
      && gesture.dy > 8 && gesture.dy > Math.abs(gesture.dx),
    onPanResponderGrant: () => translateY.stopAnimation(),
    onPanResponderMove: (_, gesture) => translateY.setValue(Math.max(0, gesture.dy)),
    onPanResponderRelease: (_, gesture) => {
      const downward = gesture.dy > Math.abs(gesture.dx);
      if (downward && (gesture.dy >= 64 || (gesture.dy >= 24 && gesture.vy > 0.7))) {
        dismissRef.current();
      }
      Animated.spring(translateY, { toValue: 0, useNativeDriver: true, overshootClamping: true }).start();
    },
    onPanResponderTerminate: () => {
      Animated.spring(translateY, { toValue: 0, useNativeDriver: true, overshootClamping: true }).start();
    },
  }), [translateY]);
  return { translateY, panHandlers: responder.panHandlers };
}
