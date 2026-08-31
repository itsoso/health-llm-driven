import { normalizeMedicalCitations } from '../medicalCitations';

describe('normalizeMedicalCitations', () => {
  it('keeps reviewed HTTPS citations and maps the server contract', () => {
    expect(normalizeMedicalCitations([
      {
        source_id: 'nhc:adult-weight-standard',
        title: '中国成人体重判定标准',
        organization: '国家卫生健康委员会',
        url: 'https://www.nhc.gov.cn/example.pdf',
        topic: 'bmi',
        claim_scope: 'BMI 公式与中国成人范围。',
      },
    ])).toEqual([
      {
        sourceId: 'nhc:adult-weight-standard',
        title: '中国成人体重判定标准',
        organization: '国家卫生健康委员会',
        url: 'https://www.nhc.gov.cn/example.pdf',
        topic: 'bmi',
        claimScope: 'BMI 公式与中国成人范围。',
      },
    ]);
  });

  it('drops insecure, malformed and duplicate citations', () => {
    expect(normalizeMedicalCitations([
      { title: '安全来源', organization: '机构', url: 'https://example.org/a' },
      { title: '重复来源', organization: '机构', url: 'https://example.org/a' },
      { title: '不安全来源', organization: '机构', url: 'http://example.org/b' },
      { title: '带凭据来源', organization: '机构', url: 'https://user:pass@example.org/c' },
      { title: '本机来源', organization: '机构', url: 'https://localhost/internal' },
      { title: '回环来源', organization: '机构', url: 'https://127.0.0.1/internal' },
      { title: '内网 IPv6 来源', organization: '机构', url: 'https://[fc00::1]/internal' },
      { title: '缺少链接', organization: '机构' },
    ])).toEqual([
      expect.objectContaining({ title: '安全来源', url: 'https://example.org/a' }),
    ]);
  });
});
