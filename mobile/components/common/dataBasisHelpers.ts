/**
 * DataBasisLine 内部纯函数, 抽到这里避免被 React/axios 链路污染单测.
 */
import { freshnessAgeDays } from '../../services/twinHelpers';

export type DataAgeTone = 'fresh' | 'stale' | 'missing';

export function formatAge(text: string | null | undefined): { hours: number | null; pretty: string } {
  if (!text) return { hours: null, pretty: '未录入' };
  const t = text.trim();

  const hMatch = t.match(/(\d+)\s*h\s*ago/i);
  if (hMatch) return { hours: parseInt(hMatch[1], 10), pretty: `${hMatch[1]} 小时前` };
  const minMatch = t.match(/(\d+)\s*min\s*ago/i);
  if (minMatch) return { hours: 0, pretty: `${minMatch[1]} 分钟前` };

  if (/今日|今天|刚刚/i.test(t)) return { hours: 0, pretty: '今日' };
  if (/昨日|昨天/i.test(t)) return { hours: 24, pretty: '昨日' };

  const days = freshnessAgeDays(t);
  if (days === null) return { hours: null, pretty: t.slice(0, 12) };
  if (days === 0) return { hours: 0, pretty: '今日' };
  if (days < 30) return { hours: days * 24, pretty: `${days} 天前` };
  if (days < 365) return { hours: days * 24, pretty: `${Math.floor(days / 30)} 月前` };
  return { hours: days * 24, pretty: `${Math.floor(days / 365)} 年前` };
}

export function ageTone(hours: number | null): DataAgeTone {
  if (hours === null) return 'missing';
  if (hours <= 12) return 'fresh';
  if (hours <= 72) return 'stale';
  return 'missing'; // 超过 3 天视同缺失 → 红
}
