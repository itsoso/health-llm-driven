/**
 * Minimal i18n bootstrap — **zh-CN only for now**.
 *
 * Why this file exists:
 *   The app hardcodes Chinese strings everywhere. If we ever need to ship
 *   English or another locale, the per-string extraction will be painful
 *   unless new code goes through `t()`. This module provides the minimum
 *   plumbing so new strings can be funneled into `strings/zh.ts` today,
 *   with zero runtime or bundle-size cost.
 *
 * Usage:
 *   import { t } from './i18n';
 *   <Text>{t('home.title')}</Text>
 *
 * Migration discipline:
 *   - NEW code: use `t()` for any user-facing string.
 *   - EXISTING code: leave hardcoded strings alone unless you're already
 *     editing that file for another reason. Full extraction is deferred.
 *   - If a key is missing, `t()` returns the key itself (visible bug signal
 *     in dev, graceful in prod).
 *
 * When to revisit:
 *   - Product commits to a second locale (English, etc.)
 *   - More than ~40% of user-facing strings flow through `t()` — then it's
 *     worth a dedicated library (i18next, lingui, formatjs).
 *   - Until then: do NOT add a library. One-file solutions are cheaper.
 */

import zh from '../strings/zh';

type Locale = 'zh';

const DICTIONARIES: Record<Locale, Record<string, string>> = { zh };

let currentLocale: Locale = 'zh';

export function setLocale(locale: Locale): void {
  currentLocale = locale;
}

export function t(key: string, params?: Record<string, string | number>): string {
  const dict = DICTIONARIES[currentLocale] ?? {};
  const raw = dict[key] ?? key;
  if (!params) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, name) =>
    params[name] !== undefined ? String(params[name]) : `{${name}}`,
  );
}

export function getLocale(): Locale {
  return currentLocale;
}
