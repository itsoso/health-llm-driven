/* eslint-disable import/first */
let mockScope = 'user-7';
let mockFailSecureWrites = false;
let mockFailSecureReads = false;
let mockFailAsyncWrites = false;
const secureValues: Record<string, string> = {};
const asyncValues: Record<string, string> = {};

jest.mock('../authStorageScope', () => ({
  getAuthStorageScope: jest.fn(async () => mockScope),
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async (key: string) => {
    if (mockFailSecureReads) throw new Error('keychain read unavailable');
    return secureValues[key] ?? null;
  }),
  setItemAsync: jest.fn(async (key: string, value: string) => {
    if (mockFailSecureWrites) throw new Error('keychain unavailable');
    secureValues[key] = value;
  }),
  deleteItemAsync: jest.fn(async (key: string) => { delete secureValues[key]; }),
}));

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(async (key: string) => asyncValues[key] ?? null),
  setItem: jest.fn(async (key: string, value: string) => {
    if (mockFailAsyncWrites) throw new Error('async storage unavailable');
    asyncValues[key] = value;
  }),
  removeItem: jest.fn(async (key: string) => { delete asyncValues[key]; }),
}));

import {
  buildCardActionReceiptIdentity,
  cardActionReceiptStorageKey,
  loadCardActionCompletion,
  loadCardActionReceipt,
  saveCardActionReceipt,
} from '../cardActionReceiptStorage';

const receipt = {
  operationId: 'diet_record.create:77',
  status: 'verified' as const,
  resourceType: 'diet_record',
  resourceId: '77',
  completedAt: '2026-07-09T12:00:00.000Z',
  verified: true as const,
};

describe('cardActionReceiptStorage', () => {
  beforeEach(() => {
    mockScope = 'user-7';
    mockFailSecureWrites = false;
    mockFailSecureReads = false;
    mockFailAsyncWrites = false;
    Object.keys(secureValues).forEach(key => delete secureValues[key]);
    Object.keys(asyncValues).forEach(key => delete asyncValues[key]);
  });

  it('restores a verified card receipt from account-scoped secure storage', async () => {
    const identity = buildCardActionReceiptIdentity({
      id: 'confirm-lunch-77',
      label: '确认记录',
      action: 'diet_record.create',
      endpoint: '/diet/records',
      payload: { record: { food_items: '鸡胸肉', meal_type: 'lunch' } },
    }, 'diet_draft');

    await saveCardActionReceipt(identity, receipt, 1_000);

    await expect(loadCardActionReceipt(identity, 2_000)).resolves.toEqual(receipt);
    const raw = secureValues[cardActionReceiptStorageKey('user-7', identity)];
    expect(raw).toBeDefined();
    expect(raw).not.toContain('鸡胸肉');
    expect(Object.keys(secureValues)).toEqual([cardActionReceiptStorageKey('user-7', identity)]);
  });

  it('does not leak a completed card action into another account', async () => {
    const identity = buildCardActionReceiptIdentity({
      id: 'confirm-42', label: '确认', action: 'write_intent.confirm',
    }, 'record');
    await saveCardActionReceipt(identity, receipt, 1_000);

    mockScope = 'user-8';
    await expect(loadCardActionReceipt(identity, 2_000)).resolves.toBeUndefined();
  });

  it('binds the same card action to its originating server message', () => {
    const action = {
      id: 'confirm-breakfast',
      label: '确认记录',
      action: 'diet_record.create',
      payload: { record: { food_items: '鸡蛋', meal_type: 'breakfast' } },
    };

    expect(buildCardActionReceiptIdentity(action, 'diet_draft', 'message-101'))
      .not.toBe(buildCardActionReceiptIdentity(action, 'diet_draft', 'message-202'));
  });

  it('keeps each encrypted receipt bounded and prunes the oldest indexed entry', async () => {
    for (let index = 0; index <= 100; index += 1) {
      await saveCardActionReceipt(`action-${index}`, {
        ...receipt,
        operationId: `diet_record.create:${index}`,
        resourceId: String(index),
      }, 1_000 + index);
    }

    expect(secureValues[cardActionReceiptStorageKey('user-7', 'action-0')]).toBeUndefined();
    expect(secureValues[cardActionReceiptStorageKey('user-7', 'action-100')]).toBeDefined();
    expect(Math.max(...Object.values(secureValues).map(value => value.length))).toBeLessThan(1_000);
  });

  it('deletes an expired encrypted receipt instead of restoring it', async () => {
    await saveCardActionReceipt('expired-action', receipt, 1_000);

    await expect(loadCardActionReceipt(
      'expired-action',
      1_000 + 91 * 24 * 60 * 60 * 1000,
    )).resolves.toBeUndefined();
    expect(secureValues[cardActionReceiptStorageKey('user-7', 'expired-action')]).toBeUndefined();
  });

  it('persists a non-sensitive completion tombstone when secure storage is unavailable', async () => {
    mockFailSecureWrites = true;

    await expect(saveCardActionReceipt('fallback-action', receipt, 1_000)).resolves.toBeUndefined();
    mockFailSecureReads = true;
    await expect(loadCardActionCompletion('fallback-action', 2_000)).resolves.toEqual({
      verified: true,
      receipt: undefined,
    });
    expect(secureValues[cardActionReceiptStorageKey('user-7', 'fallback-action')]).toBeUndefined();
    expect(JSON.stringify(asyncValues)).not.toContain(receipt.resourceId);
    expect(JSON.stringify(asyncValues)).not.toContain(receipt.operationId);
  });

  it('keeps a completed action locked during a temporary secure-store read failure', async () => {
    await saveCardActionReceipt('read-fallback-action', receipt, 1_000);
    mockFailSecureReads = true;

    await expect(loadCardActionCompletion('read-fallback-action', 2_000)).resolves.toEqual({
      verified: true,
      receipt: undefined,
    });
    expect(asyncValues).toBeDefined();
  });

  it('fails loudly when the duplicate-guard index cannot be persisted', async () => {
    mockFailAsyncWrites = true;

    await expect(saveCardActionReceipt('index-failure-action', receipt, 1_000))
      .rejects.toThrow('card_action_receipt_index_persistence_failed');
    expect(secureValues[cardActionReceiptStorageKey('user-7', 'index-failure-action')])
      .toBeDefined();

    mockFailSecureReads = true;
    await expect(loadCardActionCompletion('index-failure-action', 2_000))
      .resolves.toBeUndefined();
  });
});
