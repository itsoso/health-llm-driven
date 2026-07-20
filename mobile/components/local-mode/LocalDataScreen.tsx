import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import * as DocumentPicker from 'expo-document-picker';
import * as Sharing from 'expo-sharing';

import { useAppSession } from '../../hooks/useAppSession';
import { LocalDataLifecycle, type LocalDataExport } from '../../services/localDataLifecycle';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';
import { revaColors, revaFonts } from '../../constants/revaTheme';

export default function LocalDataScreen({ onBack }: { onBack: () => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { session, deleteLocalData } = useAppSession();
  const lifecycle = useMemo(
    () => session?.localIdentityId ? new LocalDataLifecycle(session.localIdentityId) : null,
    [session?.localIdentityId],
  );
  const [backup, setBackup] = useState<LocalDataExport | null>(null);
  const [restoreFile, setRestoreFile] = useState<{ uri: string; name: string } | null>(null);
  const [recoveryKey, setRecoveryKey] = useState('');
  const [busy, setBusy] = useState<'export' | 'restore' | 'delete' | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const createBackup = async () => {
    if (!lifecycle || busy) return;
    setBusy('export');
    setMessage(null);
    try {
      setBackup(await lifecycle.exportData());
    } catch {
      setMessage('备份没有完成，请解锁设备后重试。');
    } finally {
      setBusy(null);
    }
  };

  const shareBackup = async () => {
    if (!backup) return;
    if (!await Sharing.isAvailableAsync()) {
      setMessage('这台设备暂时无法分享文件。');
      return;
    }
    await Sharing.shareAsync(backup.fileUri, {
      mimeType: 'application/json',
      UTI: 'public.json',
      dialogTitle: '保存 Reva 本地加密备份',
    });
  };

  const copyRecoveryKey = async () => {
    if (!backup) return;
    await Clipboard.setStringAsync(backup.recoveryKey);
    setMessage('恢复密钥已复制；请不要和备份文件保存在同一处。');
  };

  const chooseRestoreFile = async () => {
    const picked = await DocumentPicker.getDocumentAsync({
      type: 'application/json',
      copyToCacheDirectory: true,
      multiple: false,
    });
    if (!picked.canceled && picked.assets[0]?.uri) {
      setRestoreFile({
        uri: picked.assets[0].uri,
        name: picked.assets[0].name || '加密恢复文件',
      });
      setMessage(null);
    }
  };

  const restore = async () => {
    if (!lifecycle || !restoreFile || !recoveryKey.trim() || busy) return;
    setBusy('restore');
    setMessage(null);
    try {
      await lifecycle.restoreData(restoreFile.uri, recoveryKey);
      setMessage('恢复完成。饮食记录已重新加密写入本机。');
      setRecoveryKey('');
    } catch (error) {
      const code = error instanceof Error ? error.message : String(error);
      setMessage(code.includes('vault_not_empty')
        ? '当前保险库不是空的，为避免重复记录已拒绝恢复。'
        : '恢复失败。请检查文件和恢复密钥是否配对。');
    } finally {
      setBusy(null);
    }
  };

  const requestDelete = () => {
    Alert.alert(
      '删除本机全部数据',
      '这会删除解密密钥和所有本地饮食记录，无备份时永久无法找回。',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '永久删除',
          style: 'destructive',
          onPress: () => {
            setBusy('delete');
            void deleteLocalData().catch((error) => {
              const code = error instanceof Error ? error.message : String(error);
              setMessage(code.includes('local_data_deleted_preference_cleanup_failed')
                ? '本地数据已删除，但运行模式配置未能重置。请重启 App 后再试。'
                : '删除没有完成，本地数据仍保留。');
              setBusy(null);
            });
          },
        },
      ],
    );
  };

  return (
    <View style={styles.safe}>
      <View style={styles.header}>
        <Pressable onPress={onBack} style={styles.headerButton} accessibilityLabel="返回本地首页">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>本地数据</Text>
        <View style={styles.headerButton} />
      </View>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Section title="加密备份" styles={styles}>
          <Text style={styles.copy}>重装或换机前必须同时保存备份文件和恢复密钥，并将两者分开存放。</Text>
          <ActionButton label="创建加密备份" busy={busy === 'export'} onPress={() => void createBackup()} styles={styles} />
          {backup ? (
            <View style={styles.resultBox}>
              <Text style={styles.resultLabel}>恢复密钥</Text>
              <Text selectable style={styles.key}>{backup.recoveryKey}</Text>
              <View style={styles.row}>
                <ActionButton label="分享恢复文件" onPress={() => void shareBackup()} styles={styles} compact />
                <ActionButton label="复制恢复密钥" onPress={() => void copyRecoveryKey()} styles={styles} compact secondary />
              </View>
            </View>
          ) : null}
        </Section>

        <Section title="恢复备份" styles={styles}>
          <Text style={styles.copy}>只能恢复到空保险库，以免重复或覆盖已有记录。</Text>
          <ActionButton label="选择恢复文件" onPress={() => void chooseRestoreFile()} styles={styles} secondary />
          {restoreFile ? <Text style={styles.fileName}>{restoreFile.name}</Text> : null}
          <TextInput
            value={recoveryKey}
            onChangeText={setRecoveryKey}
            placeholder="粘贴 44 位恢复密钥"
            placeholderTextColor={c.labelTertiary}
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
          />
          <ActionButton
            label="恢复到空保险库"
            busy={busy === 'restore'}
            disabled={!restoreFile || !recoveryKey.trim()}
            onPress={() => void restore()}
            styles={styles}
          />
        </Section>

        <Section title="永久删除" styles={styles} danger>
          <Text style={styles.dangerCopy}>删除后只能使用之前保存的备份文件和恢复密钥找回数据。</Text>
          <Pressable style={styles.deleteButton} onPress={requestDelete} disabled={busy === 'delete'}>
            {busy === 'delete' ? <ActivityIndicator color={c.red} /> : <Text style={styles.deleteText}>删除本机全部数据</Text>}
          </Pressable>
        </Section>
        {message ? <Text style={styles.message}>{message}</Text> : null}
      </ScrollView>
    </View>
  );
}

function Section({ title, styles, children, danger = false }: {
  title: string;
  styles: ReturnType<typeof createStyles>;
  children: React.ReactNode;
  danger?: boolean;
}) {
  return <View style={[styles.section, danger ? styles.dangerSection : null]}><Text style={styles.sectionTitle}>{title}</Text>{children}</View>;
}

function ActionButton({ label, onPress, styles, busy = false, disabled = false, secondary = false, compact = false }: {
  label: string;
  onPress: () => void;
  styles: ReturnType<typeof createStyles>;
  busy?: boolean;
  disabled?: boolean;
  secondary?: boolean;
  compact?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || busy}
      style={[styles.action, secondary ? styles.actionSecondary : null, compact ? styles.actionCompact : null, disabled ? styles.disabled : null]}
    >
      {busy ? <ActivityIndicator color={secondary ? styles.actionSecondaryText.color : styles.actionText.color} /> : <Text style={secondary ? styles.actionSecondaryText : styles.actionText}>{label}</Text>}
    </Pressable>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { height: 52, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { color: c.labelPrimary, fontSize: 18, fontWeight: '700' },
  content: { padding: 20, paddingBottom: 60, gap: 16 },
  section: { borderRadius: 16, padding: 16, gap: 12, backgroundColor: c.bgCard, borderWidth: 1, borderColor: c.separator },
  dangerSection: { borderColor: c.red },
  sectionTitle: { color: c.labelPrimary, fontSize: 17, fontWeight: '800' },
  copy: { color: c.labelSecondary, fontSize: 13, lineHeight: 20 },
  dangerCopy: { color: c.red, fontSize: 13, lineHeight: 20 },
  action: { minHeight: 46, borderRadius: 12, backgroundColor: c.brand, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  actionSecondary: { backgroundColor: c.brandLight },
  actionCompact: { flex: 1, minHeight: 44 },
  actionText: { color: revaColors.surface, fontSize: 14, fontWeight: '700', textAlign: 'center' },
  actionSecondaryText: { color: c.brand, fontSize: 14, fontWeight: '700', textAlign: 'center' },
  disabled: { opacity: 0.45 },
  resultBox: { gap: 10, padding: 12, borderRadius: 12, backgroundColor: c.bgPrimary },
  resultLabel: { color: c.labelSecondary, fontSize: 12, fontWeight: '700' },
  key: { color: c.labelPrimary, fontSize: 12, lineHeight: 18, fontFamily: revaFonts.mono },
  row: { flexDirection: 'row', gap: 8 },
  fileName: { color: c.brand, fontSize: 13, fontWeight: '700' },
  input: { minHeight: 46, borderRadius: 12, backgroundColor: c.bgPrimary, color: c.labelPrimary, paddingHorizontal: 12, fontFamily: revaFonts.mono },
  deleteButton: { minHeight: 46, borderRadius: 12, borderWidth: 1, borderColor: c.red, alignItems: 'center', justifyContent: 'center' },
  deleteText: { color: c.red, fontSize: 14, fontWeight: '800' },
  message: { color: c.labelSecondary, fontSize: 13, lineHeight: 19, textAlign: 'center' },
});
