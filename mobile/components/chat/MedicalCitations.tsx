import React, { useCallback, useRef } from 'react';
import {
  Alert,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { revaColors as C, revaFonts } from '../../constants/revaTheme';
import {
  safeMedicalCitationUrl,
  type MedicalCitation,
} from '../../services/medicalCitations';

interface Props {
  citations?: MedicalCitation[];
  onPaint?: () => void;
}

async function openCitation(url: string): Promise<void> {
  const safeUrl = safeMedicalCitationUrl(url);
  if (!safeUrl) return;
  try {
    await Linking.openURL(safeUrl);
  } catch {
    Alert.alert('暂时无法打开来源', '请检查网络后重试。');
  }
}

export default function MedicalCitations({ citations = [], onPaint }: Props) {
  const reportedPaintRef = useRef(false);
  const handleLayout = useCallback(() => {
    if (reportedPaintRef.current) return;
    reportedPaintRef.current = true;
    onPaint?.();
  }, [onPaint]);

  if (citations.length === 0) return null;

  return (
    <View
      testID="medical-citations"
      style={styles.container}
      accessibilityLabel="医学参考来源"
      onLayout={handleLayout}
    >
      <View style={styles.headingRow}>
        <Ionicons name="library-outline" size={14} color={C.green600} />
        <Text maxFontSizeMultiplier={2} style={styles.heading}>参考来源</Text>
      </View>
      {citations.map((citation) => (
        <Pressable
          key={`${citation.sourceId}:${citation.url}`}
          onPress={() => { void openCitation(citation.url); }}
          accessibilityRole="link"
          accessibilityLabel={`打开参考来源：${citation.title}，${citation.organization}，外部网站`}
          accessibilityHint="将在浏览器中打开官方来源"
          style={({ pressed }) => [styles.source, pressed && styles.sourcePressed]}
        >
          <View style={styles.sourceText}>
            <Text maxFontSizeMultiplier={2} style={styles.title}>{citation.title}</Text>
            <Text maxFontSizeMultiplier={2} style={styles.organization}>
              {citation.organization}
            </Text>
          </View>
          <Ionicons name="open-outline" size={15} color={C.green600} />
        </Pressable>
      ))}
      <Text maxFontSizeMultiplier={2} style={styles.boundary}>
        健康信息用于辅助管理，不替代诊断；做医疗决定前请咨询医生。
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginTop: 12,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.green50,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 7,
  },
  headingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  heading: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '700',
    color: C.green700,
  } as TextStyle,
  source: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    borderRadius: 10,
    backgroundColor: C.paper,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  sourcePressed: {
    opacity: 0.68,
  },
  sourceText: {
    flex: 1,
    gap: 2,
  },
  title: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
    color: C.ink1,
  } as TextStyle,
  organization: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink2,
  } as TextStyle,
  boundary: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink2,
  } as TextStyle,
});
