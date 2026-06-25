jest.mock('../agenda', () => ({
  __esModule: true,
  getSmartAgendaToday: jest.fn(),
  completeAgendaItem: jest.fn(),
}));

import { completeAgendaItem, getSmartAgendaToday, type SmartAgendaItem } from '../agenda';
import {
  applyRokidVoiceAgendaAction,
  isVoiceActionableAgendaItem,
  pickVoiceActionableAgendaItem,
} from '../rokidVoiceAgenda';

const mockGetSmartAgendaToday = getSmartAgendaToday as jest.MockedFunction<typeof getSmartAgendaToday>;
const mockCompleteAgendaItem = completeAgendaItem as jest.MockedFunction<typeof completeAgendaItem>;

function smartItem(overrides: Partial<SmartAgendaItem>): SmartAgendaItem {
  return {
    id: 'smart_health_protocol_1',
    type: 'hydration',
    title: '晨间喝水 2000ml',
    status: 'pending',
    priority: 50,
    source: { object_type: 'health_protocol', object_id: 1 },
    why_now: '',
    do_now: '',
    verify_by: {},
    replan_policy: {},
    surface: { primary: 'home' },
    autonomy_tier: 'suggest',
    can_complete: true,
    can_snooze: true,
    can_skip: true,
    ...overrides,
  } as SmartAgendaItem;
}

function smartTodayWith(items: SmartAgendaItem[]) {
  return {
    agenda_date: '2026-06-25',
    count: items.length,
    items: [],
    mode: 'smart' as const,
    source_count: items.length,
    smart: { top_items: items },
  };
}

describe('services/rokidVoiceAgenda', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('isVoiceActionableAgendaItem (R4 safety gate)', () => {
    it('allows non-medical-grade health_protocol items', () => {
      const item = smartItem({});
      expect(isVoiceActionableAgendaItem(item, 'confirm')).toBe(true);
      expect(isVoiceActionableAgendaItem(item, 'skip')).toBe(true);
      expect(isVoiceActionableAgendaItem(item, 'snooze')).toBe(true);
    });

    it('excludes non-protocol object_types (health_problem / daily_plan_action)', () => {
      for (const objectType of ['health_problem', 'daily_plan_action']) {
        const item = smartItem({ source: { object_type: objectType, object_id: 9 } });
        expect(isVoiceActionableAgendaItem(item, 'confirm')).toBe(false);
        expect(isVoiceActionableAgendaItem(item, 'skip')).toBe(false);
        expect(isVoiceActionableAgendaItem(item, 'snooze')).toBe(false);
      }
    });

    it('B1: excludes medication / supplement / checkup PROTOCOLS — they ride object_type=health_protocol with domain in `type`', () => {
      // 这是真实议程 shape:用药/补剂协议 object_type 仍是 'health_protocol',只有 type(domain)
      // 区分。换回只看 object_type 的旧门 → 这些会被放行 → 含糊语音写真实用药/补剂依从(R4 违规)。
      for (const domain of ['medication', 'supplement', 'checkup']) {
        const item = smartItem({ type: domain, source: { object_type: 'health_protocol', object_id: 9 } });
        expect(isVoiceActionableAgendaItem(item, 'confirm')).toBe(false);
        expect(isVoiceActionableAgendaItem(item, 'skip')).toBe(false);
        expect(isVoiceActionableAgendaItem(item, 'snooze')).toBe(false);
      }
    });

    it('fail-closed: an unknown / future protocol domain is NOT voice-actionable by default', () => {
      // 白名单语义:backend PROTOCOL_DOMAINS 将来新增 domain(如 diet/measurement/training/未知)
      // 默认不放行,依从写路径不靠「记得来加黑名单」。
      for (const domain of ['diet', 'measurement', 'training', 'exercise', 'newfangled_domain']) {
        const item = smartItem({ type: domain, source: { object_type: 'health_protocol', object_id: 9 } });
        expect(isVoiceActionableAgendaItem(item, 'confirm')).toBe(false);
      }
    });

    it('excludes confirm-tier items even when they are whitelisted-domain protocols', () => {
      const item = smartItem({ autonomy_tier: 'confirm' });
      expect(isVoiceActionableAgendaItem(item, 'confirm')).toBe(false);
    });

    it('respects per-action capability flags', () => {
      expect(isVoiceActionableAgendaItem(smartItem({ can_complete: false }), 'confirm')).toBe(false);
      expect(isVoiceActionableAgendaItem(smartItem({ can_skip: false }), 'skip')).toBe(false);
      expect(isVoiceActionableAgendaItem(smartItem({ can_snooze: false }), 'snooze')).toBe(false);
    });
  });

  describe('backend voice_actionable flag is authoritative (source_model drift defense)', () => {
    it('backend flag=false overrides a whitelisted domain → refused (the drift sentinel)', () => {
      // 真实漂移:hydration domain 在客户端白名单内,但后端看到 source_model=medication_logs
      // → voice_actionable=false。只看 domain 会放行(写真实 MedicationLog);以后端 flag 为准才挡住。
      const drift = smartItem({ type: 'hydration', voice_actionable: false });
      expect(isVoiceActionableAgendaItem(drift, 'confirm')).toBe(false);
      expect(isVoiceActionableAgendaItem(drift, 'skip')).toBe(false);
      expect(isVoiceActionableAgendaItem(drift, 'snooze')).toBe(false);
    });

    it('backend flag=true allows a non-whitelisted domain → admitted (widening to true source of truth)', () => {
      // diet 不在客户端白名单内,但后端 source_model=diet_records(非医疗级)→ voice_actionable=true。
      // 后端 flag 为权威 → 放行。证明 flag 能比保守白名单更准(既不漏挡也不错杀)。
      const diet = smartItem({ type: 'diet', voice_actionable: true });
      expect(isVoiceActionableAgendaItem(diet, 'confirm')).toBe(true);
    });

    it('backend flag=false on a medication protocol → refused (consistent with whitelist, now via flag)', () => {
      const med = smartItem({ type: 'medication', voice_actionable: false });
      expect(isVoiceActionableAgendaItem(med, 'confirm')).toBe(false);
    });

    it('autonomy_tier=confirm still wins even when backend flag=true', () => {
      const item = smartItem({ type: 'diet', voice_actionable: true, autonomy_tier: 'confirm' });
      expect(isVoiceActionableAgendaItem(item, 'confirm')).toBe(false);
    });

    it('per-action capability flags still respected even when backend flag=true', () => {
      expect(
        isVoiceActionableAgendaItem(smartItem({ voice_actionable: true, can_complete: false }), 'confirm'),
      ).toBe(false);
      expect(
        isVoiceActionableAgendaItem(smartItem({ voice_actionable: true, can_skip: false }), 'skip'),
      ).toBe(false);
    });

    it('flag is ignored for non-protocol sources (object_type gate first)', () => {
      const item = smartItem({
        voice_actionable: true,
        source: { object_type: 'health_problem', object_id: 9 },
      });
      expect(isVoiceActionableAgendaItem(item, 'confirm')).toBe(false);
    });
  });

  describe('pickVoiceActionableAgendaItem', () => {
    it('picks the highest-ranked safe item, skipping a higher-ranked medication PROTOCOL', () => {
      const items = [
        // 真实 shape:用药协议排在最前,但被 domain 白名单挡掉。
        smartItem({ type: 'medication', source: { object_type: 'health_protocol', object_id: 7 }, title: '二甲双胍' }),
        smartItem({ type: 'activity', source: { object_type: 'health_protocol', object_id: 3 }, title: '眼保健操' }),
      ];
      const picked = pickVoiceActionableAgendaItem(items, 'confirm');
      expect(picked?.source.object_id).toBe(3);
      expect(picked?.title).toBe('眼保健操');
    });

    it('returns null when the only pending item is a medication protocol', () => {
      const items = [smartItem({ type: 'medication', source: { object_type: 'health_protocol', object_id: 7 } })];
      expect(pickVoiceActionableAgendaItem(items, 'confirm')).toBeNull();
    });
  });

  describe('applyRokidVoiceAgendaAction', () => {
    it('confirm → completes the resolved protocol via the completion loop (done)', async () => {
      mockGetSmartAgendaToday.mockResolvedValueOnce(smartTodayWith([smartItem({})]));
      mockCompleteAgendaItem.mockResolvedValueOnce({} as never);

      const result = await applyRokidVoiceAgendaAction('confirm');

      expect(mockGetSmartAgendaToday).toHaveBeenCalledWith(10);
      expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
        { object_type: 'health_protocol', object_id: 1 },
        'protocol',
        undefined,
        { status: 'done' },
      );
      expect(result).toEqual({
        ok: true,
        action: 'confirm',
        wrote: true,
        item: { title: '晨间喝水 2000ml', source: { object_type: 'health_protocol', object_id: 1 } },
      });
    });

    it('skip → records skipped via the completion loop (default skip_reason)', async () => {
      mockGetSmartAgendaToday.mockResolvedValueOnce(smartTodayWith([smartItem({})]));
      mockCompleteAgendaItem.mockResolvedValueOnce({} as never);

      const result = await applyRokidVoiceAgendaAction('skip');

      expect(mockCompleteAgendaItem).toHaveBeenCalledWith(
        { object_type: 'health_protocol', object_id: 1 },
        'protocol',
        undefined,
        { status: 'skipped' },
      );
      expect(result).toMatchObject({ ok: true, action: 'skip', wrote: true });
    });

    it('snooze → does NOT write (no backend endpoint); leaves item pending', async () => {
      mockGetSmartAgendaToday.mockResolvedValueOnce(smartTodayWith([smartItem({})]));

      const result = await applyRokidVoiceAgendaAction('snooze');

      expect(mockCompleteAgendaItem).not.toHaveBeenCalled();
      expect(result).toMatchObject({ ok: true, action: 'snooze', wrote: false });
    });

    it('B1 regression: a medication PROTOCOL is the only pending item → no_target, NO adherence write', async () => {
      // 关键对抗:换回只看 object_type 的旧门 → completeAgendaItem 会被调用 → 写真实 MedicationLog。
      mockGetSmartAgendaToday.mockResolvedValueOnce(
        smartTodayWith([
          smartItem({ type: 'medication', title: '华法林 3mg', source: { object_type: 'health_protocol', object_id: 7 } }),
        ]),
      );

      const result = await applyRokidVoiceAgendaAction('confirm');

      expect(mockCompleteAgendaItem).not.toHaveBeenCalled();
      expect(result.ok).toBe(false);
      if (!result.ok) expect(result.reason).toBe('no_target');
    });

    it('skips a medication protocol via voice too (no skipped-dose write from vague voice)', async () => {
      mockGetSmartAgendaToday.mockResolvedValueOnce(
        smartTodayWith([
          smartItem({ type: 'supplement', source: { object_type: 'health_protocol', object_id: 8 } }),
        ]),
      );

      const result = await applyRokidVoiceAgendaAction('skip');

      expect(mockCompleteAgendaItem).not.toHaveBeenCalled();
      expect(result.ok).toBe(false);
    });

    it('propagates completion-loop write failures (does not fake success)', async () => {
      mockGetSmartAgendaToday.mockResolvedValueOnce(smartTodayWith([smartItem({})]));
      mockCompleteAgendaItem.mockRejectedValueOnce(new Error('完成回写失败: 422'));

      await expect(applyRokidVoiceAgendaAction('confirm')).rejects.toThrow('完成回写失败');
    });
  });
});
