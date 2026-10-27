import React from 'react';
import { Text, Button } from 'react-native';
import { Stack, router } from 'expo-router';
import { renderRouter, fireEvent } from 'expo-router/testing-library';
import TabLayout from '../app/(tabs)/_layout';
import AlertsScreen from '../app/(tabs)/alerts';
import JournalScreen from '../app/(tabs)/journal';
import AccountSecurityScreen from '../app/account-security';

jest.unmock('expo-router');
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);
jest.mock('@tanstack/react-query', () => ({ useQuery: () => ({ refetch: jest.fn() }) }));
jest.mock('../hooks/useJournalTimeline', () => ({ useJournalTimeline: () => ({ refetch: jest.fn() }) }));
jest.mock('../hooks/useToast', () => ({ useToast: () => ({ show: jest.fn() }) }));
jest.mock('../hooks/useAuth', () => ({ useAuth: () => ({ user: { has_password: true } }) }));
jest.mock('../services/clientEvents', () => ({ emitClientEvent: jest.fn() }));
jest.mock('../services/auth', () => ({ changePassword: jest.fn(), setPassword: jest.fn() }));

const routes = {
  _layout: () => <Stack screenOptions={{ headerShown: false }}>
    <Stack.Screen name="settings" options={{ presentation: 'modal' }} />
    <Stack.Screen name="account-security" options={{ presentation: 'modal' }} />
  </Stack>,
  '(tabs)/_layout': { default: TabLayout, unstable_settings: { initialRouteName: 'chat' } },
  '(tabs)/chat': () => <Button title="打开设置" onPress={() => router.push('/settings')} />,
  '(tabs)/index': () => <Text>index</Text>,
  '(tabs)/today': () => <Text>today</Text>,
  '(tabs)/record': () => <Text>record</Text>,
  '(tabs)/me': () => <Text>me</Text>,
  '(tabs)/alerts': AlertsScreen,
  '(tabs)/journal/index': JournalScreen,
  settings: () => <>
    <Button title="打开安全" onPress={() => router.push('/alerts')} />
    <Button title="打开日记" onPress={() => router.push('/journal')} />
    <Button title="打开账号安全" onPress={() => router.push('/account-security')} />
  </>,
  'account-security': AccountSecurityScreen,
};

describe('real router menu round trips', () => {
  it.each([['打开安全', '/alerts'], ['打开日记', '/journal']])('returns home after settings → %s', (entry, path) => {
    const view = renderRouter(routes, { initialUrl: '/chat' });
    fireEvent.press(view.getByText('打开设置'));
    expect(view.getPathname()).toBe('/settings');
    fireEvent.press(view.getByText(entry));
    expect(view.getPathname()).toBe(path);
    fireEvent.press(view.getByRole('button', { name: '返回小气候' }));
    expect(view.getPathname()).toBe('/chat');
    expect(view.getByText('打开设置')).toBeTruthy();
  });
  it('preserves the settings caller of account security', () => {
    const view = renderRouter(routes, { initialUrl: '/chat' });
    fireEvent.press(view.getByText('打开设置'));
    fireEvent.press(view.getByText('打开账号安全'));
    fireEvent.press(view.getByRole('button', { name: '返回' }));
    expect(view.getPathname()).toBe('/settings');
  });
  it('provides a home exit for a cold account-security link', () => {
    const view = renderRouter(routes, { initialUrl: '/account-security' });
    fireEvent.press(view.getByRole('button', { name: '返回' }));
    expect(view.getPathname()).toBe('/chat');
  });
});
