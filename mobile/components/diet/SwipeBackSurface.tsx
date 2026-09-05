import React, { useEffect, useMemo, useRef } from 'react';
import {
  Animated,
  PanResponder,
  StyleSheet,
  useWindowDimensions,
  type GestureResponderEvent,
  type PanResponderGestureState,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

const EDGE_START_DISTANCE = 28;
const CLAIM_DISTANCE = 10;
const COMPLETE_DISTANCE = 88;
const COMPLETE_VELOCITY = 0.8;
const HORIZONTAL_INTENT_RATIO = 1.2;

function hasHorizontalEdgeSwipeIntent(
  gesture: PanResponderGestureState,
  initialX: number,
): boolean {
  return initialX <= EDGE_START_DISTANCE
    && gesture.dx >= CLAIM_DISTANCE
    && gesture.dx >= Math.abs(gesture.dy) * HORIZONTAL_INTENT_RATIO;
}

function isEdgeSwipeIntent(
  gesture: PanResponderGestureState,
  initialX: number,
): boolean {
  return gesture.numberActiveTouches === 1
    && hasHorizontalEdgeSwipeIntent(gesture, initialX);
}

function completesEdgeSwipe(
  gesture: PanResponderGestureState,
  initialX: number,
): boolean {
  // React Native reports zero active touches in onPanResponderRelease. Single-
  // touch eligibility was already enforced while claiming the responder, so
  // the release decision must rely on the recorded edge start and trajectory.
  return hasHorizontalEdgeSwipeIntent(gesture, initialX)
    && (gesture.dx >= COMPLETE_DISTANCE || gesture.vx >= COMPLETE_VELOCITY);
}

export type SwipeBackSurfaceProps = {
  children: React.ReactNode;
  onBack: () => void;
  enabled?: boolean;
  resetBeforeBack?: boolean;
  style?: StyleProp<ViewStyle>;
  testID: string;
};

/**
 * Adds an iOS-style, left-edge back gesture without bypassing the owning
 * screen's confirmation or cleanup path. Constraining the gesture to the edge
 * prevents it from competing with photo pan, pinch, and privacy drawing.
 */
export function SwipeBackSurface({
  children,
  onBack,
  enabled = true,
  resetBeforeBack = false,
  style,
  testID,
}: SwipeBackSurfaceProps) {
  const translateX = useRef(new Animated.Value(0)).current;
  const backTriggeredRef = useRef(false);
  const initialXRef = useRef(Number.POSITIVE_INFINITY);
  const { width: windowWidth } = useWindowDimensions();
  const latestRef = useRef({ enabled, onBack, resetBeforeBack, windowWidth });
  latestRef.current = { enabled, onBack, resetBeforeBack, windowWidth };

  useEffect(() => {
    if (enabled) return;
    backTriggeredRef.current = false;
    translateX.stopAnimation();
    translateX.setValue(0);
  }, [enabled, translateX]);

  const panResponder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => false,
    onStartShouldSetPanResponderCapture: (event: GestureResponderEvent) => {
      const firstTouch = event.nativeEvent.touches[0];
      initialXRef.current = firstTouch?.pageX ?? event.nativeEvent.pageX;
      return latestRef.current.enabled
        && event.nativeEvent.touches.length === 1
        && initialXRef.current <= EDGE_START_DISTANCE;
    },
    onMoveShouldSetPanResponderCapture: (
      _event: GestureResponderEvent,
      gesture: PanResponderGestureState,
    ) => latestRef.current.enabled && isEdgeSwipeIntent(gesture, initialXRef.current),
    onPanResponderGrant: () => {
      backTriggeredRef.current = false;
      translateX.stopAnimation();
    },
    onPanResponderMove: (_event, gesture) => {
      if (!latestRef.current.enabled) return;
      translateX.setValue(Math.max(0, gesture.dx));
    },
    onPanResponderRelease: (_event, gesture) => {
      if (
        !latestRef.current.enabled
        || !completesEdgeSwipe(gesture, initialXRef.current)
      ) {
        Animated.spring(translateX, {
          toValue: 0,
          damping: 22,
          stiffness: 240,
          mass: 0.8,
          useNativeDriver: true,
        }).start();
        return;
      }

      if (backTriggeredRef.current) return;
      backTriggeredRef.current = true;
      if (latestRef.current.resetBeforeBack) {
        translateX.setValue(0);
      } else {
        Animated.timing(translateX, {
          toValue: Math.max(320, latestRef.current.windowWidth),
          duration: 180,
          useNativeDriver: true,
        }).start();
      }
      latestRef.current.onBack();
    },
    onPanResponderTerminate: () => {
      initialXRef.current = Number.POSITIVE_INFINITY;
      Animated.spring(translateX, {
        toValue: 0,
        damping: 22,
        stiffness: 240,
        mass: 0.8,
        useNativeDriver: true,
      }).start();
    },
    onPanResponderTerminationRequest: () => false,
  }), [translateX]);

  const opacity = translateX.interpolate({
    inputRange: [0, Math.max(320, windowWidth)],
    outputRange: [1, 0.88],
    extrapolate: 'clamp',
  });

  return (
    <Animated.View
      testID={testID}
      accessibilityState={{ disabled: !enabled }}
      style={[styles.surface, style, { opacity, transform: [{ translateX }] }]}
      {...panResponder.panHandlers}
    >
      {children}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  surface: {
    flex: 1,
  },
});
