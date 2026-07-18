import { BPCardSpec } from '../BPCard';

describe('BPCardSpec.build', () => {
  it('renders the server-provided severe-reading status and guidance without reclassifying locally', async () => {
    const api = { get: jest.fn().mockResolvedValue({ data: [{
      systolic: 185,
      diastolic: 85,
      record_date: '2026-07-18',
      category: '血压严重升高',
      category_color: '#B42318',
      safety_guidance: {
        severity: 'high',
        recheck_instruction: '请静坐至少 1 分钟后复测。',
        emergency_instruction: '若同时出现胸痛，请立即拨打急救电话。',
        action_path: '/blood-pressure',
      },
    }] }) };

    const card = await BPCardSpec.build({
      query: '血压',
      query_lower: '血压',
      toolsUsed: new Set(),
      data: {},
      api,
    });

    expect(api.get).toHaveBeenCalledWith('/blood-pressure/records/me', { params: { limit: 1 } });
    expect(card).toMatchObject({
      category: '血压严重升高',
      category_color: '#B42318',
      safety_guidance: { severity: 'high', action_path: '/blood-pressure' },
    });
  });
});
