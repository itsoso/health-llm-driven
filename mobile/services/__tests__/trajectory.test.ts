import api from '../api';
import { getHealthTrajectory, pickPrimaryTrajectoryRisks } from '../trajectory';

jest.mock('../api', () => ({
  get: jest.fn(),
}));

const mockedApi = api as jest.Mocked<typeof api>;

describe('trajectory service', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('loads the personal health trajectory snapshot', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: {
        focus_domains: ['metabolic_health', 'recovery_capacity', 'aging_pace'],
        generated_at: '2026-05-15T00:00:00Z',
        trajectory_risks: [
          {
            domain: 'metabolic_health',
            level: 'attention',
            title: '中心性肥胖轨迹',
            evidence_tier: 'clinical_guideline',
            confidence: 'high',
            claim_boundary: '用于健康管理, 不替代医生诊断。',
          },
        ],
        data_gaps: [{ code: 'methylation_report_missing', label: '缺甲基化报告' }],
      },
    });

    const result = await getHealthTrajectory();

    expect(mockedApi.get).toHaveBeenCalledWith('/trajectory/me');
    expect(result.trajectory_risks).toHaveLength(1);
    expect(result.trajectory_risks[0].evidence_tier).toBe('clinical_guideline');
    expect(result.trajectory_risks[0].confidence).toBe('high');
    expect(result.data_gaps[0].code).toBe('methylation_report_missing');
  });

  it('prioritizes actionable risks before unknown states', () => {
    const risks = pickPrimaryTrajectoryRisks([
      { domain: 'aging_pace', level: 'unknown', title: '缺少甲基化反馈' },
      { domain: 'recovery_capacity', level: 'attention', title: '恢复能力偏低' },
      { domain: 'metabolic_health', level: 'high', title: '血压轨迹偏高' },
    ]);

    expect(risks.map(r => r.domain)).toEqual(['metabolic_health', 'recovery_capacity', 'aging_pace']);
  });
});
