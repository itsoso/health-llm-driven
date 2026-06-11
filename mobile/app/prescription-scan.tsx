/**
 * /prescription-scan —— 上传医生处方 → 识别药品 → 查对应原研药。
 *
 * 流程:拍照/选图 → POST /prescriptions/recognize → 展示每种药的「处方名 / 通用名 /
 * 原研药(品牌+厂家)」。原研药来自后端精选表(不靠 LLM 编),未收录的明确标"暂无数据"。
 * 仅供参考,具体以药师/医生为准。
 */
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import * as Haptics from 'expo-haptics';

import {
  recognizePrescription,
  sortByOriginator,
  summarize,
  type PrescriptionRecognizeResult,
  type PrescriptionDrug,
} from '../services/prescriptions';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

function DrugCard({ drug }: { drug: PrescriptionDrug }) {
  const { c } = useTheme();
  const styles = createStyles(c);
  const o = drug.originator;
  return (
    <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.cardTop}>
        <Text style={[styles.rxName, { color: c.labelPrimary }]} numberOfLines={2}>
          {drug.raw_name || drug.generic_name || '未知药品'}
        </Text>
        {(drug.dosage || drug.frequency) && (
          <Text style={[styles.spec, { color: c.labelTertiary }]} numberOfLines={1}>
            {[drug.dosage, drug.frequency].filter(Boolean).join(' · ')}
          </Text>
        )}
        {drug.generic_name && drug.generic_name !== drug.raw_name && (
          <Text style={[styles.generic, { color: c.labelSecondary }]} numberOfLines={1}>
            通用名:{drug.generic_name}
          </Text>
        )}
      </View>

      <View style={[styles.origBox, { backgroundColor: c.fill }]}>
        {o ? (
          <>
            <View style={styles.origHeader}>
              <Ionicons name="ribbon-outline" size={14} color={c.brand} />
              <Text style={[styles.origLabel, { color: c.brand }]}>对应原研药</Text>
            </View>
            <Text style={[styles.origBrand, { color: c.labelPrimary }]}>{o.brand}</Text>
            <Text style={[styles.origMfr, { color: c.labelTertiary }]}>{o.manufacturer}</Text>
          </>
        ) : (
          <Text style={[styles.origMfr, { color: c.labelTertiary }]}>暂无原研药数据(未收录,不臆测)</Text>
        )}
      </View>
    </View>
  );
}

export default function PrescriptionScanScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = createStyles(c);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PrescriptionRecognizeResult | null>(null);

  const run = async (uri: string, name: string, mime: string) => {
    setLoading(true);
    setResult(null);
    try {
      const r = await recognizePrescription(uri, name, mime);
      setResult(r);
    } catch (e: any) {
      Alert.alert('识别失败', e?.response?.data?.detail ?? e?.message ?? '请换一张更清晰的处方照片');
    } finally {
      setLoading(false);
    }
  };

  const takePhoto = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { Alert.alert('需要相机权限'); return; }
    const picked = await ImagePicker.launchCameraAsync({ quality: 0.7 });
    if (picked.canceled || !picked.assets?.[0]) return;
    const a = picked.assets[0];
    run(a.uri, a.fileName || 'rx.jpg', a.mimeType || 'image/jpeg');
  };

  const pickImage = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) { Alert.alert('需要相册权限'); return; }
    const picked = await ImagePicker.launchImageLibraryAsync({ quality: 0.7 });
    if (picked.canceled || !picked.assets?.[0]) return;
    const a = picked.assets[0];
    run(a.uri, a.fileName || 'rx.jpg', a.mimeType || 'image/jpeg');
  };

  const drugs = sortByOriginator(result?.items);

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={[styles.title, { color: c.labelPrimary }]}>处方查原研药</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.actions}>
          <TouchableOpacity style={[styles.actionBtn, { backgroundColor: c.brand }]} onPress={takePhoto} disabled={loading}>
            <Ionicons name="camera" size={18} color="#fff" />
            <Text style={styles.actionText}>拍处方</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.actionBtn, { backgroundColor: c.fill }]} onPress={pickImage} disabled={loading}>
            <Ionicons name="image-outline" size={18} color={c.labelPrimary} />
            <Text style={[styles.actionText, { color: c.labelPrimary }]}>从相册选</Text>
          </TouchableOpacity>
        </View>

        {loading && (
          <View style={{ alignItems: 'center', marginTop: 40 }}>
            <ActivityIndicator color={c.brand} />
            <Text style={[styles.hint, { color: c.labelTertiary, marginTop: 10 }]}>识别中…(OCR + 原研药匹配)</Text>
          </View>
        )}

        {!loading && !result && (
          <Text style={[styles.hint, { color: c.labelTertiary, marginTop: 24 }]}>
            拍下或上传医生处方,自动识别药品并查询对应的原研药(原厂品牌)。{'\n'}原研药数据来自精选表,未收录的会标"暂无数据",不臆测。
          </Text>
        )}

        {!loading && result && (
          <>
            <Text style={[styles.summary, { color: c.labelSecondary }]}>{summarize(result)}</Text>
            {drugs.map((d, i) => <DrugCard key={`${d.raw_name}-${i}`} drug={d} />)}
            <Text style={[styles.disclaimer, { color: c.labelTertiary }]}>{result.note}</Text>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) =>
  StyleSheet.create({
    safe: { flex: 1 },
    header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
    title: { fontSize: 17, fontWeight: '700' },
    content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.md },
    actions: { flexDirection: 'row', gap: 12 },
    actionBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 46, borderRadius: radii.lg },
    actionText: { color: '#fff', fontSize: 15, fontWeight: '700' },
    hint: { fontSize: 13, lineHeight: 19, textAlign: 'center', paddingHorizontal: spacing.md },
    summary: { fontSize: 13, fontWeight: '600', marginBottom: 2 },
    card: { borderRadius: radii.lg, borderWidth: StyleSheet.hairlineWidth, padding: spacing.md, gap: 10 },
    cardTop: { gap: 3 },
    rxName: { fontSize: 15, fontWeight: '800' },
    spec: { fontSize: 12, fontWeight: '500' },
    generic: { fontSize: 12, fontWeight: '500' },
    origBox: { borderRadius: radii.md, padding: 10, gap: 2 },
    origHeader: { flexDirection: 'row', alignItems: 'center', gap: 5 },
    origLabel: { fontSize: 11, fontWeight: '700' },
    origBrand: { fontSize: 15, fontWeight: '800' },
    origMfr: { fontSize: 12, fontWeight: '500' },
    disclaimer: { fontSize: 11, lineHeight: 15, marginTop: 4 },
  });
