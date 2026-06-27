import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { CardShell } from './CardShell';
import { revaColors as C, revaSemantic, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';

// 睡眠阶段的装饰性 hue (深睡靛蓝 / REM 紫 / 浅睡品紫 / 清醒琥珀) ——「分阶段」色码,
// 非「好坏」临床语义, 故保留字面量. tintPurple 卡底同理 (= legacy #EDE7F6).
const STAGE_DEEP = '#5856D6';
const STAGE_REM = '#7C5CBF';
const STAGE_LIGHT = '#AF52DE';
const STAGE_AWAKE = '#C98A1E';
const CARD_TINT = '#EDE7F6';

interface SleepData {
  score?: number;
  duration_h?: number;
  deep_min?: number;
  rem_min?: number;
  light_min?: number;
  awake_min?: number;
}

function ScoreRing({ score, fillTrack }: { score: number; fillTrack: string }) {
  const size = 52, sw = 5;
  const r = (size - sw) / 2;
  const circ = 2 * Math.PI * r;
  const off = circ * (1 - Math.min(score / 100, 1));
  // 睡眠评分 = 真正的「好坏」语义 → Reva 三步临床色 normal/caution/risk
  const color = score >= 80 ? revaSemantic.normal.fg : score >= 60 ? revaSemantic.caution.fg : revaSemantic.risk.fg;
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size}>
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={fillTrack} strokeWidth={sw} fill="none" />
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={sw} fill="none"
          strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off}
          transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      </Svg>
      <Text maxFontSizeMultiplier={1.3} style={[styles.scoreNum, { color }]}>{score}</Text>
    </View>
  );
}

function Stage({ label, min, color }: { label: string; min?: number; color: string }) {
  if (min == null) return null;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return (
    <View style={styles.stage}>
      <View style={[styles.stageDot, { backgroundColor: color }]} />
      <Text maxFontSizeMultiplier={1.3} style={styles.stageLabel}>{label}</Text>
      <Text maxFontSizeMultiplier={1.3} style={styles.stageVal}>
        {h > 0 ? `${h}h${m}m` : `${m}m`}
      </Text>
    </View>
  );
}

export function SleepCardView({ score, duration_h, deep_min, rem_min, light_min, awake_min }: SleepData) {
  return (
    <CardShell icon="moon" iconColor={STAGE_REM} title="睡眠分析" bg={CARD_TINT}>
      <View style={styles.row}>
        {score != null && <ScoreRing score={score} fillTrack={C.paper2} />}
        <View style={{ flex: 1, marginLeft: 12 }}>
          {duration_h != null && (
            <Text maxFontSizeMultiplier={1.3} style={styles.duration}>
              {duration_h.toFixed(1)}h
            </Text>
          )}
          <View style={styles.stages}>
            <Stage label="深睡" min={deep_min} color={STAGE_DEEP} />
            <Stage label="REM" min={rem_min} color={STAGE_REM} />
            <Stage label="浅睡" min={light_min} color={STAGE_LIGHT} />
            <Stage label="清醒" min={awake_min} color={STAGE_AWAKE} />
          </View>
        </View>
      </View>
    </CardShell>
  );
}

export const SleepCardSpec: CardSpec<SleepData> = {
  type: 'sleep',
  label: '睡眠分析',
  match({ query_lower }) {
    if (/记录|打卡/.test(query_lower)) return null;
    if (/睡眠|深睡|rem|浅睡|睡得|入睡|清醒/.test(query_lower)) return 20;
    return null;
  },
  build({ data }) {
    const g = data.garmin;
    if (!g) return null;
    const cardData: SleepData = {};
    if (g.sleep_score != null) cardData.score = g.sleep_score;
    if (g.total_sleep_duration) cardData.duration_h = g.total_sleep_duration / 60;
    if (g.deep_sleep_duration != null) cardData.deep_min = Math.round(g.deep_sleep_duration);
    if (g.rem_sleep_duration != null) cardData.rem_min = Math.round(g.rem_sleep_duration);
    if (g.light_sleep_duration != null) cardData.light_min = Math.round(g.light_sleep_duration);
    if (g.awake_duration != null) cardData.awake_min = Math.round(g.awake_duration);
    return Object.keys(cardData).length > 0 ? cardData : null;
  },
  render: (d) => <SleepCardView {...d} />,
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center' },
  stages: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 4 },
  stage: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  stageDot: { width: 6, height: 6, borderRadius: 3 },
  scoreNum: { fontFamily: revaFonts.mono, fontSize: 16, fontWeight: '800', position: 'absolute', fontVariant: ['tabular-nums'] as const } as TextStyle,
  duration: { fontFamily: revaFonts.mono, fontSize: 18, fontWeight: '800', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
  stageLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink2 } as TextStyle,
  stageVal: { fontFamily: revaFonts.mono, fontSize: 10, fontWeight: '600', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
});
