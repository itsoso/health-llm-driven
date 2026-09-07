/* eslint-disable import/first */
// Exercise the real auth entry points through the real API interceptor and
// egress policy. Only the transport/native storage are replaced: an endpoint
// constant snapshot cannot catch a UI flow switching to a new auth endpoint.
let mockRequestInterceptor: (config: any) => Promise<any>;
const mockTransport = jest.fn();

jest.mock('axios', () => ({
  __esModule: true,
  default: {
    create: () => ({
      interceptors: {
        request: { use: (handler: typeof mockRequestInterceptor) => { mockRequestInterceptor = handler; } },
        response: { use: jest.fn() },
      },
      post: async (url: string, data: unknown) => {
        const config = await mockRequestInterceptor({
          method: 'post', url, data,
          headers: { get: () => undefined, delete: jest.fn() },
        });
        return mockTransport(config);
      },
    }),
  },
}));
jest.mock('../../modules/shared-keychain', () => ({
  saveTokenToSharedKeychain: jest.fn(),
  deleteTokenFromSharedKeychain: jest.fn(),
  readTokenFromSharedKeychain: jest.fn(),
}));
jest.mock('../registrationInviteStorage', () => ({
  clearPendingRegistration: jest.fn(),
  createPendingRegistration: jest.fn(),
  loadPendingRegistration: jest.fn(async () => ({
    verifiedPhoneTicket: 'synthetic-verified-ticket',
    idempotencyKey: 'synthetic-registration-attempt',
  })),
}));

import * as SecureStore from 'expo-secure-store';
import {
  login, requestPhoneCode, loginByPhoneCode, verifyPhoneCode,
  completeInvitedRegistration,
} from '../auth';
import { setRuntimeAuthToken } from '../api';
import { setAppEgressMode } from '../egressPolicy';

const transportReached = new Error('synthetic_transport_reached');

beforeEach(() => {
  jest.clearAllMocks();
  setRuntimeAuthToken(null);
  setAppEgressMode(null);
  (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);
  // Stop at the transport boundary; no real request or login token is created.
  mockTransport.mockRejectedValue(transportReached);
});

it.each([
  ['account password', '/auth/login/json', () => login('synthetic-reviewer', 'synthetic-password')],
  ['request SMS', '/auth/phone/code', () => requestPhoneCode('+8613800000000')],
  ['legacy SMS login', '/auth/phone/login', () => loginByPhoneCode('+8613800000000', '123456')],
  ['verify SMS', '/auth/phone/verify', () => verifyPhoneCode('+8613800000000', '123456')],
  ['manual invitation', '/auth/invited-registration', () => completeInvitedRegistration({ manualCode: 'ABCD1234' })],
  ['invitation link', '/auth/invited-registration', () => completeInvitedRegistration({ linkToken: 'synthetic-link' })],
] as const)('allows unauthenticated %s through the actual auth service', async (_name, url, invoke) => {
  await expect(invoke()).rejects.toBe(transportReached);
  expect(mockTransport).toHaveBeenCalledTimes(1);
  expect(mockTransport).toHaveBeenCalledWith(expect.objectContaining({ method: 'post', url }));
});

it.each([
  ['get', '/auth/phone/verify'],
  ['post', '/auth/phone/verify/extra'],
  ['post', '/auth/invited-registration/extra'],
  ['post', '/auth/me/deletion-request'],
  ['put', '/auth/ai-consent'],
  ['post', '/agent/chat'],
])('does not broaden logged-out access to %s %s', async (method, url) => {
  await expect(mockRequestInterceptor({
    method, url, headers: { get: () => undefined, delete: jest.fn() },
  })).rejects.toMatchObject({ code: 'cloud_session_required' });
  expect(mockTransport).not.toHaveBeenCalled();
});
