import { describe, expect, it } from 'vitest';
import {
  buildSharedMetadata,
  isSensitiveSharedConversation,
  publicSiteBaseUrl,
} from './sharePrivacy';

describe('share privacy helpers', () => {
  it('marks genetic, medication, and diagnosis content as sensitive', () => {
    expect(isSensitiveSharedConversation({
      title: '基因报告解读',
      messages: [{ role: 'assistant', content: 'ATP7B 和 CFTR 位点需要复核，涉及用药安全。' }],
    })).toBe(true);
  });

  it('keeps non-health menu shares readable by default', () => {
    expect(isSensitiveSharedConversation({
      title: '晚餐菜单',
      messages: [{ role: 'assistant', content: '今晚吃鱼 + 米饭 + 青菜。' }],
    })).toBe(false);
  });

  it('uses generic metadata and absolute production image for sensitive shares', () => {
    const metadata = buildSharedMetadata({
      title: '我的基因报告',
      sensitive: true,
      firstMessage: 'APOE 和 ATP7B 风险分析全文',
    });

    expect(metadata.description).toBe('这是一条包含健康敏感信息的用户分享，打开后需确认查看。');
    expect(metadata.imageUrl).toBe('https://health.executor.life/logo-512.png');
    expect(metadata.description).not.toContain('APOE');
  });

  it('normalizes public site base url without localhost fallback', () => {
    expect(publicSiteBaseUrl('http://localhost:30001')).toBe('https://health.executor.life');
    expect(publicSiteBaseUrl('https://health.executor.life/')).toBe('https://health.executor.life');
  });
});
