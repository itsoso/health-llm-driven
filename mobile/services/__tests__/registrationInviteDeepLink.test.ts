import * as Linking from 'expo-linking';
import { act, renderHook, waitFor } from '@testing-library/react-native';

import {
  getInitialRegistrationInviteToken,
  parseRegistrationInviteToken,
  subscribeToRegistrationInviteLinks,
  useRegistrationInviteDeepLink,
} from '../registrationInviteDeepLink';

jest.mock('expo-linking', () => ({
  getInitialURL: jest.fn(),
  addEventListener: jest.fn(),
}));

const token = 'abcdefghijklmnopqrstuvwxyz_123456';
const backendCanonicalLink = `health://invite?token=${token}`;

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('registration invite deep links', () => {
  beforeEach(() => jest.clearAllMocks());

  it.each([
    [backendCanonicalLink],
    [`mobile://invite?token=${token}`],
  ])('accepts only the app invite target: %s', (url) => {
    expect(parseRegistrationInviteToken(url)).toBe(token);
  });

  it.each([
    [`https://evil.example/invite?token=${token}`],
    [`health://other?token=${token}`],
    [`health://invite/extra?token=${token}`],
    ['health://invite?token=short'],
    [`health://invite?token=${token}&phone=13800138000`],
    [`health://invite?token=${encodeURIComponent(`${token}!`)}`],
    [`health://invite?token=${token}#unexpected`],
    [`health://user@invite?token=${token}`],
  ])('ignores malformed or over-scoped links: %s', (url) => {
    expect(parseRegistrationInviteToken(url)).toBeNull();
  });

  it('loads a valid initial URL without returning the URL itself', async () => {
    (Linking.getInitialURL as jest.Mock).mockResolvedValue(`health://invite?token=${token}`);

    await expect(getInitialRegistrationInviteToken()).resolves.toBe(token);
  });

  it('forwards valid runtime tokens and removes its listener on cleanup', () => {
    const remove = jest.fn();
    let listener: ((event: { url: string }) => void) | undefined;
    (Linking.addEventListener as jest.Mock).mockImplementation((_name, next) => {
      listener = next;
      return { remove };
    });
    const onToken = jest.fn();

    const cleanup = subscribeToRegistrationInviteLinks(onToken);
    listener?.({ url: `health://invite?token=${token}` });
    listener?.({ url: `health://other?token=${token}` });
    cleanup();

    expect(onToken).toHaveBeenCalledTimes(1);
    expect(onToken).toHaveBeenCalledWith(token);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it('keeps a newer runtime credential when the deferred initial URL resolves later', async () => {
    const remove = jest.fn();
    let listener: ((event: { url: string }) => void) | undefined;
    const initial = deferred<string | null>();
    (Linking.getInitialURL as jest.Mock).mockReturnValue(initial.promise);
    (Linking.addEventListener as jest.Mock).mockImplementation((_name, next) => {
      listener = next;
      return { remove };
    });

    const view = renderHook(() => useRegistrationInviteDeepLink());
    const runtimeToken = 'zyxwvutsrqponmlkjihgfedc_654321';
    act(() => listener?.({ url: `mobile://invite?token=${runtimeToken}` }));
    expect(view.result.current.token).toBe(runtimeToken);
    await act(async () => initial.resolve(`health://invite?token=${token}`));
    expect(view.result.current.token).toBe(runtimeToken);
    act(() => view.result.current.clear());
    expect(view.result.current.token).toBeNull();
    view.unmount();
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it('handles initial-link lookup failure without logging a credential-bearing error', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    (Linking.getInitialURL as jest.Mock).mockRejectedValue(
      new Error(`native failure for health://invite?token=${token}`),
    );
    (Linking.addEventListener as jest.Mock).mockReturnValue({ remove: jest.fn() });

    const view = renderHook(() => useRegistrationInviteDeepLink());
    await waitFor(() => expect(warn).toHaveBeenCalledWith(
      '[RegistrationInvite] initial URL unavailable',
    ));
    expect(view.result.current.token).toBeNull();
    expect(warn).not.toHaveBeenCalledWith(expect.stringContaining(token));
    view.unmount();
    warn.mockRestore();
  });
});
