import '@testing-library/jest-native/extend-expect';

// Legacy service tests exercise the existing cloud-account paths directly.
// Individual local-mode tests override this explicitly and verify fail-closed behavior.
require('./services/egressPolicy').setAppEgressMode('cloud_account');

// Jest runs in a Node environment where Axios may select its fetch adapter.
// Axios's fetch adapter performs a ReadableStream capability probe that can
// trigger an unhandled rejection with Expo's virtual ReadableStream
// implementation (observed on Node.js v25). Force Node's spec-compliant
// ReadableStream for test stability.
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { ReadableStream } = require('stream/web');
  (globalThis as any).ReadableStream = ReadableStream;
} catch {
  // ignore
}

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn().mockResolvedValue(null),
  setItemAsync: jest.fn().mockResolvedValue(undefined),
  deleteItemAsync: jest.fn().mockResolvedValue(undefined),
}));

jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium', Heavy: 'heavy' },
}));

jest.mock('react-native-reanimated', () => {
  const React = require('react');
  const RN = require('react-native');
  const createAnimatedComponent = (Component: any) => {
    const MockAnimatedComponent = React.forwardRef((props: any, ref: any) =>
      React.createElement(Component, { ...props, ref }, props.children)
    );
    MockAnimatedComponent.displayName = `Animated(${Component.displayName || Component.name || 'Component'})`;
    return MockAnimatedComponent;
  };
  const instantAnimation = (value: unknown, _config?: unknown, callback?: (finished: boolean) => void) => {
    callback?.(true);
    return value;
  };
  const Animated = {
    View: createAnimatedComponent(RN.View),
    Text: createAnimatedComponent(RN.Text),
    Image: createAnimatedComponent(RN.Image),
    ScrollView: createAnimatedComponent(RN.ScrollView),
    createAnimatedComponent,
  };
  const identity = (value: unknown) => value;

  return {
    __esModule: true,
    default: Animated,
    createAnimatedComponent,
    Easing: {
      linear: identity,
      ease: identity,
      bezier: () => identity,
      in: identity,
      out: identity,
      inOut: identity,
    },
    useSharedValue: (value: unknown) => ({ value }),
    useAnimatedProps: (factory: () => unknown) => factory(),
    useAnimatedStyle: (factory: () => unknown) => factory(),
    useDerivedValue: (factory: () => unknown) => ({ value: factory() }),
    withTiming: instantAnimation,
    withSpring: instantAnimation,
    withDelay: (_delayMs: number, value: unknown) => value,
    withRepeat: (value: unknown) => value,
    withSequence: (...values: unknown[]) => values[values.length - 1],
    runOnJS: (fn: (...args: unknown[]) => unknown) => fn,
  };
});

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), replace: jest.fn() }),
  useLocalSearchParams: () => ({}),
  usePathname: () => '/',
  Link: 'Link',
  Stack: { Screen: 'Screen' },
}));

jest.mock('@expo/vector-icons/Ionicons', () => {
  const React = require('react');
  const { View } = require('react-native');
  return React.forwardRef((props: any, ref: any) =>
    React.createElement(View, { ...props, ref, testID: `icon-${props.name}` })
  );
});

jest.mock('@expo/vector-icons', () => {
  const React = require('react');
  const { View } = require('react-native');
  const MockIcon = React.forwardRef((props: any, ref: any) =>
    React.createElement(View, { ...props, ref, testID: `icon-${props.name}` })
  );
  MockIcon.displayName = 'MockIcon';
  return {
    Ionicons: MockIcon,
    MaterialIcons: MockIcon,
    MaterialCommunityIcons: MockIcon,
    FontAwesome: MockIcon,
  };
});

jest.mock('react-native-svg', () => {
  const React = require('react');
  const { View } = require('react-native');
  const mock = (name: string) => (props: any) => React.createElement(View, { ...props, testID: name });
  return {
    __esModule: true,
    default: mock('Svg'),
    Svg: mock('Svg'),
    Rect: mock('Rect'),
    Circle: mock('Circle'),
    Line: mock('Line'),
    Polygon: mock('Polygon'),
    Path: mock('Path'),
    G: mock('G'),
    Text: mock('SvgText'),
    Polyline: mock('Polyline'),
    // 渐变三件套:ReadinessRing 等用 <Defs><LinearGradient><Stop> 画环。缺它们 → 具名导入为
    // undefined → "Element type is invalid. Check the render method of ReadinessRing"(整套件挂)。
    Defs: mock('Defs'),
    LinearGradient: mock('LinearGradient'),
    Stop: mock('Stop'),
  };
});

jest.mock('./modules/shared-keychain', () => ({
  saveTokenToSharedKeychain: jest.fn().mockResolvedValue(true),
  deleteTokenFromSharedKeychain: jest.fn().mockResolvedValue(undefined),
  readTokenFromSharedKeychain: jest.fn().mockResolvedValue(null),
}));

jest.mock('react-native-safe-area-context', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    SafeAreaView: (props: any) => React.createElement(View, props),
    SafeAreaProvider: (props: any) => React.createElement(View, props),
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});

jest.mock('@react-native-community/netinfo', () => ({
  addEventListener: jest.fn(() => jest.fn()),
  fetch: jest.fn().mockResolvedValue({ isConnected: true }),
}));
