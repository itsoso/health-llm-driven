import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
} from '../../constants/revaTheme';
import {
  formatDurationMs,
  type AgentTransparencyBand,
  type AgentTransparencyProfile,
} from '../../utils/chatTransparency';
import { SocialBrandIcon } from '../common/SocialBrandIcon';
import { AttributionDetails, normalizedAttributionCount } from './AttributionChips';

type ProcessTone = 'complete' | 'warning';

interface ProcessItem {
  label: string;
  tone: ProcessTone;
}

interface EvidenceSummary {
  title: string;
  subtitle: string;
  tone: ProcessTone;
}

interface Props {
  profile: AgentTransparencyProfile;
  sources?: readonly string[];
  thinkingSteps: readonly string[];
  sharingEnabled: boolean;
  onOpenMemory: () => void;
  onShareWeChat: () => void;
  onShareXiaohongshu: () => void;
  onCopy: () => void;
  copied: boolean;
}

const WARNING_STEP = /失败|不可用|缺失|未找到|没有找到|未同步|未完成|跳过|暂停|超时|错误|无法/;

function completedProcessLabel(raw: string): string {
  const cleaned = String(raw || '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[.…]+$/, '');
  if (!cleaned) return '';
  if (/^(?:正在)?思考(?:你的问题)?$/.test(cleaned)) return '理解你的问题';
  if (/^(?:正在)?理解你的问题$/.test(cleaned)) return '理解你的问题';
  if (/^(?:正在)?整理(?:回复|回答|思路)(?:中)?$/.test(cleaned)) return '整理回答';
  if (/^(?:已)?(?:取得|获取|读取)(?:到)?健康数据$/.test(cleaned)) return '检查健康数据';
  return cleaned.replace(/^正在/, '').replace(/中$/, '').trim();
}

export function buildEvidenceProcessItems(steps: readonly string[]): ProcessItem[] {
  const seen = new Set<string>();
  const items: ProcessItem[] = [];
  for (const raw of steps) {
    const label = completedProcessLabel(raw);
    if (!label || seen.has(label)) continue;
    seen.add(label);
    items.push({ label, tone: WARNING_STEP.test(label) ? 'warning' : 'complete' });
  }
  return items;
}

export function buildEvidenceSummary(
  sourceCount: number,
  processItems: readonly ProcessItem[],
): EvidenceSummary {
  const completeCount = processItems.filter(item => item.tone === 'complete').length;
  const warningCount = processItems.length - completeCount;
  const tone: ProcessTone = warningCount > 0 ? 'warning' : 'complete';

  if (sourceCount > 0) {
    const subtitle = warningCount > 0
      ? completeCount > 0
        ? `完成 ${completeCount} 个处理步骤，${warningCount} 项需要注意`
        : `${warningCount} 项处理需要注意`
      : completeCount > 0
        ? `已完成 ${completeCount} 个处理步骤，可继续核对技术信息`
        : '来源保留在这里，方便随时核对';
    return {
      title: `这条回答参考了 ${sourceCount} 项信息`,
      subtitle,
      tone,
    };
  }

  if (warningCount > 0) {
    return {
      title: completeCount > 0
        ? `完成 ${completeCount} 个处理步骤，${warningCount} 项需要注意`
        : `${warningCount} 项处理需要注意`,
      subtitle: '请查看处理摘要，必要时核对技术信息',
      tone,
    };
  }

  return {
    title: completeCount > 0
      ? `这条回答完成了 ${completeCount} 个处理步骤`
      : '这条回答的生成记录',
    subtitle: completeCount > 0
      ? '可查看处理摘要与技术信息'
      : '可查看技术信息',
    tone,
  };
}

function bandColor(kind: AgentTransparencyBand['kind']): string {
  switch (kind) {
    case 'prellm': return '#CBD5D1';
    case 'ttft': return '#D99A2B';
    case 'gen': return C.green500;
    case 'tool': return C.blue500;
    case 'orch': return revaSemantic.risk.fg;
    case 'total':
    default:
      return C.green300;
  }
}

export default function AnswerEvidencePanel({
  profile,
  sources,
  thinkingSteps,
  sharingEnabled,
  onOpenMemory,
  onShareWeChat,
  onShareXiaohongshu,
  onCopy,
  copied,
}: Props) {
  const [open, setOpen] = useState(false);
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const sourceCount = normalizedAttributionCount(sources);
  const processItems = useMemo(() => buildEvidenceProcessItems(thinkingSteps), [thinkingSteps]);
  const evidenceSummary = useMemo(
    () => buildEvidenceSummary(sourceCount, processItems),
    [processItems, sourceCount],
  );
  const technicalRows = [
    ...(profile.routing.length > 0 ? [{ label: '模型选择', value: profile.routing.join(' · ') }] : []),
    ...(profile.stages.length > 0 ? [{ label: '准备阶段', value: profile.stages.map(s => `${s.label} ${s.value}`).join(' · ') }] : []),
    ...(profile.rounds.length > 0 ? [{ label: '处理轮次', value: profile.rounds.map(r => `${r.label} ${r.value}`).join('\n') }] : []),
    ...(profile.costLine ? [{ label: '成本估算', value: profile.costLine }] : []),
    ...(profile.tokenLine ? [{ label: 'Token', value: profile.tokenLine }] : []),
    ...(profile.errorLine ? [{ label: '失败信息', value: profile.errorLine }] : []),
    ...(profile.traceLine ? [{ label: '追踪信息', value: profile.traceLine }] : []),
  ];
  const hasTechnicalDetails = !!profile.headline
    || profile.bands.length > 0
    || technicalRows.length > 0
    || profile.tools.length > 0
    || (sourceCount === 0 && profile.sources.length > 0);
  const hasDetails = sourceCount > 0 || processItems.length > 0 || hasTechnicalDetails;
  const hasWarning = evidenceSummary.tone === 'warning';

  return (
    <View testID="assistant-utility-panel" style={styles.panel}>
      <View style={styles.rail}>
        {hasDetails ? (
          <Pressable
            onPress={() => setOpen(value => !value)}
            style={({ pressed }) => [styles.evidenceButton, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={open ? '收起回答依据' : '展开回答依据'}
            accessibilityState={{ expanded: open }}
          >
            <View style={styles.railIcon}>
              <Ionicons name="document-text-outline" size={13} color={C.green700} />
            </View>
            <Text style={txt.evidenceLabel} numberOfLines={1}>
              {`回答依据${sourceCount > 0 ? ` · ${sourceCount}项` : ''}`}
            </Text>
            <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={13} color={C.ink3} />
          </Pressable>
        ) : <View style={styles.spacer} />}

        {sharingEnabled ? (
          <>
            <View style={styles.divider} />
            <Pressable
              onPress={onShareWeChat}
              accessibilityRole="button"
              accessibilityLabel="微信分享这条回复"
              style={({ pressed }) => [styles.shareButton, pressed && styles.pressed]}
            >
              <SocialBrandIcon brand="wechat" size={20} />
            </Pressable>
            <Pressable
              onPress={onShareXiaohongshu}
              accessibilityRole="button"
              accessibilityLabel="小红书分享这条回复"
              style={({ pressed }) => [styles.shareButton, pressed && styles.pressed]}
            >
              <SocialBrandIcon brand="xiaohongshu" size={20} />
            </Pressable>
          </>
        ) : null}

        <Pressable
          onPress={onCopy}
          accessibilityRole="button"
          accessibilityLabel={copied ? '已复制' : '复制回答'}
          hitSlop={6}
          style={({ pressed }) => [
            styles.copyButton,
            copied && styles.copyButtonDone,
            pressed && styles.pressed,
          ]}
        >
          <Ionicons name={copied ? 'checkmark' : 'copy-outline'} size={14} color={copied ? C.green700 : C.ink3} />
        </Pressable>
      </View>

      {open && hasDetails ? (
        <View style={styles.details}>
          <View style={styles.summary}>
            <View style={[styles.summaryIcon, hasWarning && styles.summaryIconWarning]}>
              <Ionicons
                name={hasWarning ? 'alert-circle-outline' : 'shield-checkmark-outline'}
                size={17}
                color={hasWarning ? revaSemantic.caution.fg : C.green700}
              />
            </View>
            <View style={styles.summaryCopy}>
              <Text style={txt.summaryTitle}>{evidenceSummary.title}</Text>
              <Text style={[txt.summarySubtitle, hasWarning && txt.summarySubtitleWarning]}>
                {evidenceSummary.subtitle}
              </Text>
            </View>
          </View>

          {sourceCount > 0 ? (
            <View style={styles.section}>
              <SectionTitle icon="file-tray-full-outline" label="参考的数据" />
              <AttributionDetails sources={sources} onOpenMemory={onOpenMemory} />
            </View>
          ) : null}

          {processItems.length > 0 ? (
            <View style={styles.section}>
              <SectionTitle icon="git-merge-outline" label="处理摘要" />
              <View style={styles.processList}>
                {processItems.map((item, index) => {
                  const warning = item.tone === 'warning';
                  return (
                    <View
                      key={item.label}
                      style={styles.processRow}
                      accessibilityLabel={warning ? `需要注意：${item.label}` : `已完成：${item.label}`}
                    >
                      <View style={[styles.processIcon, warning && styles.processIconWarning]}>
                        <Ionicons
                          name={warning ? 'alert' : 'checkmark'}
                          size={10}
                          color={warning ? revaSemantic.caution.fg : '#FFFFFF'}
                        />
                      </View>
                      <Text style={[txt.processLabel, warning && txt.processLabelWarning]}>{item.label}</Text>
                      {index < processItems.length - 1 ? <View style={styles.processConnector} /> : null}
                    </View>
                  );
                })}
              </View>
            </View>
          ) : null}

          {hasTechnicalDetails ? (
            <View style={styles.technicalCard}>
              <Pressable
                onPress={() => setTechnicalOpen(value => !value)}
                style={({ pressed }) => [styles.technicalHeader, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityLabel={technicalOpen ? '收起技术详情' : '展开技术详情'}
                accessibilityState={{ expanded: technicalOpen }}
              >
                <Ionicons name="options-outline" size={14} color={C.ink3} />
                <Text style={txt.technicalTitle}>技术详情</Text>
                <Text style={txt.technicalHint}>按需查看</Text>
                <Ionicons name={technicalOpen ? 'chevron-up' : 'chevron-down'} size={13} color={C.ink3} />
              </Pressable>

              {technicalOpen ? (
                <View style={styles.technicalBody}>
                  {profile.headline ? <Text style={txt.mono}>{profile.headline}</Text> : null}
                  {profile.bands.length > 0 ? (
                    <>
                      <View style={styles.timingBar}>
                        {profile.bands.map((band, index) => (
                          <View
                            key={`${band.kind}-${index}`}
                            style={{
                              flexGrow: band.ratio,
                              flexBasis: 0,
                              backgroundColor: bandColor(band.kind),
                            }}
                          />
                        ))}
                      </View>
                      <View style={styles.timingLegend}>
                        {profile.bands.map((band, index) => (
                          <Text key={`${band.kind}-legend-${index}`} style={txt.mono}>
                            {band.label} {formatDurationMs(band.ms)}
                          </Text>
                        ))}
                      </View>
                    </>
                  ) : null}

                  {technicalRows.map(row => (
                    <View key={row.label} style={styles.technicalRow}>
                      <Text style={txt.technicalLabel}>{row.label}</Text>
                      <Text style={txt.technicalValue}>{row.value}</Text>
                    </View>
                  ))}

                  {profile.sources.length > 0 && sourceCount === 0 ? (
                    <View style={styles.technicalRow}>
                      <Text style={txt.technicalLabel}>引用数据</Text>
                      <View style={styles.technicalValueList}>
                        {profile.sources.slice(0, 8).map(source => (
                          <Text key={source} style={txt.technicalValue}>· {source}</Text>
                        ))}
                      </View>
                    </View>
                  ) : null}

                  {profile.tools.length > 0 ? (
                    <View style={styles.technicalRow}>
                      <Text style={txt.technicalLabel}>{profile.toolLabel === '调用 Skill' ? '调用工具' : '尝试调用工具'}</Text>
                      <View style={styles.toolRow}>
                        {profile.tools.map(tool => (
                          <View key={tool} style={styles.toolChip}>
                            <Text style={txt.toolLabel}>{tool}</Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  ) : null}
                </View>
              ) : null}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

function SectionTitle({ icon, label }: { icon: React.ComponentProps<typeof Ionicons>['name']; label: string }) {
  return (
    <View style={styles.sectionTitleRow}>
      <Ionicons name={icon} size={14} color={C.green700} />
      <Text style={txt.sectionTitle}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { alignSelf: 'stretch', width: '100%', marginTop: 12 },
  rail: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 12,
    backgroundColor: C.paper2,
    paddingHorizontal: 4,
    gap: 2,
  },
  evidenceButton: {
    minHeight: 44,
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: 7,
  },
  railIcon: {
    width: 23,
    height: 23,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  spacer: { flex: 1 },
  divider: { width: StyleSheet.hairlineWidth, height: 18, backgroundColor: C.line },
  shareButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper,
  },
  copyButton: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper,
  },
  copyButtonDone: { backgroundColor: C.green50 },
  pressed: { opacity: 0.76 },
  details: {
    marginTop: 8,
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: '#FBFCF9',
    padding: 13,
    gap: 16,
  },
  summary: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  summaryIcon: {
    width: 34,
    height: 34,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  summaryIconWarning: {
    backgroundColor: revaSemantic.caution.bg,
    borderColor: revaSemantic.caution.line,
  },
  summaryCopy: { flex: 1, minWidth: 0, gap: 2 },
  section: { gap: 9 },
  sectionTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  processList: { paddingLeft: 2, gap: 8 },
  processRow: { minHeight: 22, flexDirection: 'row', alignItems: 'flex-start', gap: 8, position: 'relative' },
  processIcon: {
    width: 17,
    height: 17,
    marginTop: 1,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green600,
    zIndex: 1,
  },
  processIconWarning: {
    backgroundColor: revaSemantic.caution.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
  },
  processConnector: {
    position: 'absolute',
    left: 8,
    top: 18,
    bottom: -9,
    width: StyleSheet.hairlineWidth,
    backgroundColor: C.green100,
  },
  technicalCard: {
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper,
    overflow: 'hidden',
  },
  technicalHeader: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: 11,
  },
  technicalBody: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
    paddingHorizontal: 11,
    paddingVertical: 10,
    gap: 9,
  },
  timingBar: {
    height: 6,
    borderRadius: revaRadii.pill,
    flexDirection: 'row',
    overflow: 'hidden',
    backgroundColor: C.line,
  },
  timingLegend: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  technicalRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  technicalValueList: { flex: 1, gap: 3 },
  toolRow: { flex: 1, flexDirection: 'row', flexWrap: 'wrap', gap: 5 },
  toolChip: {
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper2,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
});

const txt = {
  evidenceLabel: { flex: 1, minWidth: 0, fontFamily: revaFonts.sans, fontSize: 11.8, lineHeight: 16, fontWeight: '800', color: C.ink2 } as TextStyle,
  summaryTitle: { fontFamily: revaFonts.sans, fontSize: 13, lineHeight: 18, fontWeight: '900', color: C.ink1 } as TextStyle,
  summarySubtitle: { fontFamily: revaFonts.sans, fontSize: 10.8, lineHeight: 16, color: C.ink3 } as TextStyle,
  summarySubtitleWarning: { color: revaSemantic.caution.fg, fontWeight: '700' } as TextStyle,
  sectionTitle: { fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 15, fontWeight: '900', color: C.ink2 } as TextStyle,
  processLabel: { flex: 1, fontFamily: revaFonts.sans, fontSize: 11.8, lineHeight: 18, fontWeight: '700', color: C.ink2 } as TextStyle,
  processLabelWarning: { color: revaSemantic.caution.fg } as TextStyle,
  technicalTitle: { flex: 1, fontFamily: revaFonts.sans, fontSize: 11.2, lineHeight: 16, fontWeight: '800', color: C.ink2 } as TextStyle,
  technicalHint: { fontFamily: revaFonts.sans, fontSize: 10, lineHeight: 14, color: C.ink3 } as TextStyle,
  technicalLabel: { width: 66, fontFamily: revaFonts.sans, fontSize: 10.5, lineHeight: 16, color: C.ink3 } as TextStyle,
  technicalValue: { flex: 1, fontFamily: revaFonts.sans, fontSize: 10.5, lineHeight: 16, fontWeight: '700', color: C.ink2 } as TextStyle,
  mono: { fontFamily: revaFonts.mono, fontSize: 10, lineHeight: 15, color: C.ink3 } as TextStyle,
  toolLabel: { fontFamily: revaFonts.sans, fontSize: 10.2, lineHeight: 14, fontWeight: '700', color: C.ink2 } as TextStyle,
};
