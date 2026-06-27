import '@testing-library/jest-native/extend-expect';

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
  const ReactNative = require('react-native');
  const id = (value: any) => value;
  const immediate = (factory: () => unknown) => factory();
  return {
    __esModule: true,
    default: {
      View: ReactNative.View,
      Text: ReactNative.Text,
      Image: ReactNative.Image,
      ScrollView: ReactNative.ScrollView,
      FlatList: ReactNative.FlatList,
      createAnimatedComponent: id,
    },
    Easing: {
      bezier: jest.fn(() => id),
      linear: id,
    },
    runOnJS: (fn: (...args: unknown[]) => unknown) => fn,
    useAnimatedProps: immediate,
    useAnimatedStyle: immediate,
    useSharedValue: (initial: unknown) => ({ value: initial }),
    withDelay: (_delay: number, animation: unknown) => animation,
    withRepeat: (animation: unknown) => animation,
    withSequence: (...animations: unknown[]) => animations[animations.length - 1],
    withSpring: id,
    withTiming: id,
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
