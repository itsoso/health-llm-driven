/**
 * Rokid 眼镜语音「当前待处理动作」解析 + 完成 / 跳过 / 稍后。
 *
 * 背景:眼镜语音 "确认 / 跳过 / 等会"(backend `route_rokid_voice_command` 的
 * `confirm_current` / `skip_current` / `snooze_current`)需要落到一个具体的待办上。Rokid
 * 健康屏自身不跟踪「当前待办」,所以这里从统一议程脊柱(`GET /agenda/today?mode=smart`)
 * 解析「最相关的待办」,再经既有完成回路写真实记录。
 *
 * 安全(R4 / under-alarm 防御 —— 这是依从写路径):
 * - **安全裁决以后端权威 `voice_actionable` flag 为准**(见 `isVoiceActionableAgendaItem`):
 *   后端从协议 `source_model`(完成实际落哪张业务表)派生 —— 完成会写医疗级依从
 *   (`MedicationLog`/`SupplementRecord`)或为复查项 → false。`source_model` 是 `_write_domain_record`
 *   分派的真相,与 domain **结构上可漂移**(如 hydration-domain 协议带 source_model=medication_logs),
 *   且只有后端看得见 —— 把安全决定钉在那里,消除「客户端 domain 白名单 ↔ 后端写表」两份清单漂移。
 *   **关键(B1)**:用药 / 补剂协议在议程里 `object_type` 同样是 `'health_protocol'`,只有 domain
 *   (及 source_model)区分 —— 单看 `object_type` 拦不住,完成它会写真实依从记录。
 * - **旧后端兜底**:后端未发该 flag 时回退到 domain 白名单(`VOICE_ACTIONABLE_DOMAINS`,fail-closed:
 *   medication / supplement / checkup / diet / measurement / 未知 domain 一律不放行)。
 *   叠加 `autonomy_tier !== 'confirm'` 与各动作 `can_*` 能力门。需要时用户在手机上显式操作。
 * - 命中的待办标题会回报给调用方(语音播报 / CustomView),让这条写「被用户听见」、可纠正。
 * - 完成 / 跳过经 `completeAgendaItem` → `POST /agenda/complete` 完成回路:DB 原子认领、幂等、
 *   防虚高依从(见 timeline_agenda_service.complete_agenda_event)。本文件不自己保证幂等。
 * - snooze 后端**无端点**(完成回路仅 done|skipped)→ 不写任何东西,待办保持 pending,下次议程 /
 *   推送自然再现(对齐 `behaviorLoopReminders` 的「稍后 → null, 行动保持待办」)。绝不假装写了
 *   一条 snooze 记录。
 */
import {
  completeAgendaItem,
  getSmartAgendaToday,
  type AgendaSource,
  type SmartAgendaItem,
} from './agenda';

export type RokidAgendaVoiceAction = 'confirm' | 'skip' | 'snooze';

/**
 * 可被含糊语音执行的安全 domain **白名单**(fail-closed)。
 *
 * 为什么是白名单而非 `object_type` 检查:用药 / 补剂协议在议程里 `object_type` 仍是
 * `'health_protocol'`,只有 `type`(= 协议 domain,见 backend agenda_service `_to_smart_item`)
 * 才区分出 `'medication'` / `'supplement'`。单看 `object_type` 拦不住 —— 完成一个 medication
 * domain 的协议会经 `complete_protocol → _write_domain_record` 写真实 `MedicationLog(status=taken)`
 * /`SupplementRecord(taken=True)`,正是 R4 禁止的「含糊语音自动写医疗级依从」(safety review B1)。
 *
 * 只放行明确低风险的行为习惯 domain(喝水/睡眠/情绪/活动/上气道护理);medication / supplement /
 * checkup / diet / measurement / training 等一律不在白名单内。backend `PROTOCOL_DOMAINS` 将来新增
 * domain 时默认**不**放行 —— 依从写路径 fail-closed,绝不让未知 domain 凭一句 "确认" 自动写。
 */
const VOICE_ACTIONABLE_DOMAINS = new Set<string>([
  'hydration',
  'sleep',
  'mood',
  'activity',
  'respiratory',
]);

export type RokidAgendaVoiceResult =
  | {
      ok: true;
      action: RokidAgendaVoiceAction;
      /** confirm/skip 真写了一条记录;snooze 恒 false(不写,保持 pending)。 */
      wrote: boolean;
      item: { title: string; source: AgendaSource };
    }
  | {
      ok: false;
      reason: 'no_target';
      message: string;
    };

const NO_TARGET_MESSAGE = '现在没有可用语音确认的待处理动作，请在手机上查看议程。';

/**
 * 该 smart 议程项能否被语音 `action` 安全执行。
 * 只放行非医疗级协议待办;med/supp/checkup/daily_plan_action 与 confirm-tier 一律排除。
 *
 * 安全裁决的权威落点是**后端** `voice_actionable`(从协议 `source_model` 派生:完成会写
 * 医疗级依从 MedicationLog/SupplementRecord、或为复查项 → false)。后端写表分派(source_model)
 * 与 domain 结构上可漂移(如 hydration-domain 协议带 source_model=medication_logs),只有
 * 后端能看见 source_model —— 故以后端 flag 为准,客户端 domain 白名单仅作旧后端缺该字段时的
 * fail-closed 兜底,消除「客户端白名单 ↔ 后端写表」两份清单漂移的风险(B1 升级版)。
 */
export function isVoiceActionableAgendaItem(
  item: SmartAgendaItem,
  action: RokidAgendaVoiceAction,
): boolean {
  if (item.source?.object_type !== 'health_protocol') return false;
  // 后端权威 flag 存在 → 以它为准(能挡住 domain 白名单漏掉的 source_model 漂移);
  // 不存在(旧后端)→ 回退 domain 白名单(fail-closed:未知 domain 不放行)。
  const backendFlag = item.voice_actionable;
  const safeToWrite =
    typeof backendFlag === 'boolean' ? backendFlag : VOICE_ACTIONABLE_DOMAINS.has(item.type ?? '');
  if (!safeToWrite) return false;
  if (item.autonomy_tier === 'confirm') return false;
  if (action === 'confirm') return item.can_complete === true;
  if (action === 'skip') return item.can_skip === true;
  return item.can_snooze === true; // snooze
}

/**
 * 从已按 rank 排序的 smart top_items 里取第一条可语音执行的安全待办。
 * 取最高排名(= 后端「下一个最该做的事」),无命中 → null。
 */
export function pickVoiceActionableAgendaItem(
  items: SmartAgendaItem[],
  action: RokidAgendaVoiceAction,
): SmartAgendaItem | null {
  for (const item of items) {
    if (isVoiceActionableAgendaItem(item, action)) return item;
  }
  return null;
}

/**
 * 解析「当前待办」并执行语音动作。
 * - 无可执行待办 → `{ ok: false, reason: 'no_target' }`(调用方据此 fail-loud,不假装完成)。
 * - confirm → 完成回路写 done;skip → 写 skipped;snooze → 不写(保持 pending)。
 * - 写失败(completeAgendaItem 抛)直接上抛,交调用方 fail-loud + 诊断,不在这里吞。
 */
export async function applyRokidVoiceAgendaAction(
  action: RokidAgendaVoiceAction,
): Promise<RokidAgendaVoiceResult> {
  // 取较宽的 top list(上限 10),避免「最相关协议」被排在被排除项(用药/复查)之下时漏掉。
  const data = await getSmartAgendaToday(10);
  const topItems = data?.smart?.top_items ?? [];
  const item = pickVoiceActionableAgendaItem(topItems, action);
  if (!item) {
    return { ok: false, reason: 'no_target', message: NO_TARGET_MESSAGE };
  }

  const title = item.title || '当前动作';
  const source = item.source;

  if (action === 'confirm') {
    await completeAgendaItem(source, 'protocol', undefined, { status: 'done' });
    return { ok: true, action, wrote: true, item: { title, source } };
  }
  if (action === 'skip') {
    // skipReason 省略 → completeAgendaItem 默认 'no_time'(语音跳过无上下文,避免无原因跳过污染分析)。
    await completeAgendaItem(source, 'protocol', undefined, { status: 'skipped' });
    return { ok: true, action, wrote: true, item: { title, source } };
  }

  // snooze:后端无端点,不写;待办保持 pending,下次自然再现。
  return { ok: true, action: 'snooze', wrote: false, item: { title, source } };
}
