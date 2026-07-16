import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import * as Updates from 'expo-updates';

import api from './api';

export type ReleasePolicySource = 'remote' | 'safe_default';

export type ReleasePolicy = {
  config_version: number;
  platform: string;
  channel: string;
  ota_enabled: boolean;
  rollout_percent: number;
  minimum_native_build: string | null;
  recommended_native_build: string | null;
  forced_update: boolean;
  kill_switches: Record<string, boolean>;
  rollback_update_id: string | null;
  expires_at: string | null;
  source: ReleasePolicySource;
};

type ReleasePolicyStore = {
  getItem: (key: string) => Promise<string | null>;
  setItem: (key: string, value: string) => Promise<void>;
};

type ReleasePolicyClient = {
  get: (path: string, config: { params: Record<string, string> }) => Promise<{ data: unknown }>;
};

type LoadReleasePolicyOptions = {
  client?: ReleasePolicyClient;
  store?: ReleasePolicyStore;
  platform?: string;
  channel?: string;
  now?: () => number;
};

type ReleasePolicyRolloutOptions = {
  store?: ReleasePolicyStore;
  random?: () => number;
};

export const RELEASE_POLICY_STORAGE_KEY = 'xiaoba.release_policy.v1';
export const RELEASE_COHORT_STORAGE_KEY = 'xiaoba.release_cohort.v1';

export const SAFE_RELEASE_POLICY: Omit<ReleasePolicy, 'platform' | 'channel'> = {
  config_version: 0,
  ota_enabled: true,
  rollout_percent: 100,
  minimum_native_build: null,
  recommended_native_build: null,
  forced_update: false,
  kill_switches: {},
  rollback_update_id: null,
  expires_at: null,
  source: 'safe_default',
};

const defaultStore: ReleasePolicyStore = {
  getItem: (key) => SecureStore.getItemAsync(key),
  setItem: (key, value) => SecureStore.setItemAsync(key, value),
};

const defaultClient: ReleasePolicyClient = {
  get: (path, config) => api.get(path, config),
};

function safeDefault(platform: string, channel: string): ReleasePolicy {
  return { ...SAFE_RELEASE_POLICY, platform, channel };
}

function isExpired(value: string | null, now: number): boolean {
  if (!value) return false;
  const parsed = Date.parse(value);
  return !Number.isFinite(parsed) || parsed <= now;
}

function isPolicy(value: unknown, now: number): value is ReleasePolicy {
  if (!value || typeof value !== 'object') return false;
  const policy = value as Partial<ReleasePolicy>;
  const validPolicy = policy as ReleasePolicy;
  if (
    !Number.isInteger(validPolicy.config_version) || validPolicy.config_version < 0
    || typeof policy.platform !== 'string'
    || typeof policy.channel !== 'string'
    || typeof policy.ota_enabled !== 'boolean'
    || !Number.isInteger(validPolicy.rollout_percent)
    || validPolicy.rollout_percent < 0
    || validPolicy.rollout_percent > 100
    || typeof policy.forced_update !== 'boolean'
    || (policy.minimum_native_build !== null && typeof policy.minimum_native_build !== 'string')
    || (policy.recommended_native_build !== null && typeof policy.recommended_native_build !== 'string')
    || (policy.rollback_update_id !== null && typeof policy.rollback_update_id !== 'string')
    || (policy.expires_at !== null && typeof policy.expires_at !== 'string')
    || (policy.source !== 'remote' && policy.source !== 'safe_default')
    || !policy.kill_switches
    || typeof policy.kill_switches !== 'object'
  ) {
    return false;
  }
  if (isExpired(validPolicy.expires_at, now)) return false;
  return Object.entries(validPolicy.kill_switches).every(
    ([key, enabled]) => /^[a-z0-9][a-z0-9_.:-]{0,63}$/.test(key) && typeof enabled === 'boolean',
  );
}

async function readCachedPolicy(
  store: ReleasePolicyStore,
  platform: string,
  channel: string,
  now: number,
): Promise<ReleasePolicy> {
  try {
    const raw = await store.getItem(RELEASE_POLICY_STORAGE_KEY);
    if (!raw) return safeDefault(platform, channel);
    const cached: unknown = JSON.parse(raw);
    if (!isPolicy(cached, now)) return safeDefault(platform, channel);
    if (cached.platform !== platform || cached.channel !== channel) {
      return safeDefault(platform, channel);
    }
    return cached;
  } catch {
    return safeDefault(platform, channel);
  }
}

/** Keep rollout assignment stable per installation without using account or health data. */
export async function getReleasePolicyRolloutBucket(
  options: ReleasePolicyRolloutOptions = {},
): Promise<number> {
  const store = options.store ?? defaultStore;
  const random = options.random ?? Math.random;
  try {
    const cached = await store.getItem(RELEASE_COHORT_STORAGE_KEY);
    const parsed = cached === null ? NaN : Number.parseInt(cached, 10);
    if (Number.isInteger(parsed) && parsed >= 0 && parsed < 100) return parsed;
    const bucket = Math.min(99, Math.max(0, Math.floor(random() * 100)));
    await store.setItem(RELEASE_COHORT_STORAGE_KEY, String(bucket));
    return bucket;
  } catch {
    return Math.min(99, Math.max(0, Math.floor(random() * 100)));
  }
}

function compareNativeBuilds(current: string, minimum: string): number | null {
  if (!/^\d+$/.test(current) || !/^\d+$/.test(minimum)) return null;
  const currentNumber = Number(current);
  const minimumNumber = Number(minimum);
  if (!Number.isSafeInteger(currentNumber) || !Number.isSafeInteger(minimumNumber)) return null;
  return currentNumber - minimumNumber;
}

/** Fail closed when a rollout or native compatibility guard does not match. */
export function isReleasePolicyEligible(
  policy: ReleasePolicy,
  nativeBuild: string,
  rolloutBucket: number,
): boolean {
  if (!policy.ota_enabled || policy.rollout_percent <= 0) return false;
  if (!Number.isInteger(rolloutBucket) || rolloutBucket < 0 || rolloutBucket >= 100) return false;
  if (rolloutBucket >= policy.rollout_percent) return false;
  if (policy.minimum_native_build) {
    const comparison = compareNativeBuilds(nativeBuild, policy.minimum_native_build);
    if (comparison === null || comparison < 0) return false;
  }
  return true;
}

export async function loadReleasePolicy(
  options: LoadReleasePolicyOptions = {},
): Promise<ReleasePolicy> {
  const platform = (options.platform ?? Platform.OS).toLowerCase();
  const channel = (options.channel ?? Updates.channel ?? 'production').toLowerCase();
  const now = options.now ?? Date.now;
  const store = options.store ?? defaultStore;
  const client = options.client ?? defaultClient;

  try {
    const response = await client.get('/app-release-policy', {
      params: { platform, channel },
    });
    const candidate: unknown = response.data;
    if (!isPolicy(candidate, now())) {
      return readCachedPolicy(store, platform, channel, now());
    }
    if (candidate.platform !== platform || candidate.channel !== channel) {
      return readCachedPolicy(store, platform, channel, now());
    }
    await store.setItem(RELEASE_POLICY_STORAGE_KEY, JSON.stringify(candidate));
    return candidate;
  } catch {
    return readCachedPolicy(store, platform, channel, now());
  }
}
