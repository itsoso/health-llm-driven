import { useState, useCallback } from 'react';
import { Alert } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';

export interface PendingImage {
  uri: string;
  base64: string;
  type: string;
}

export function useMediaPicker() {
  const [pendingImage, setPendingImage] = useState<PendingImage | null>(null);
  const [pickedFileName, setPickedFileName] = useState<string | null>(null);

  const clearPendingImage = useCallback(() => setPendingImage(null), []);

  const pickImage = useCallback(async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相册权限', '请在系统设置中允许 HealthPilot 访问相册');
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        base64: true,
        quality: 0.8,
      });
      if (!result.canceled && result.assets[0]) {
        const a = result.assets[0];
        setPendingImage({
          uri: a.uri,
          base64: a.base64 || '',
          type: a.mimeType?.split('/')[1] || 'jpeg',
        });
      }
    } catch (e) {
      Alert.alert('选择图片失败', String(e));
    }
  }, []);

  const takePhoto = useCallback(async () => {
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相机权限', '请在系统设置中允许 HealthPilot 使用相机');
        return;
      }
      const result = await ImagePicker.launchCameraAsync({
        base64: true,
        quality: 0.8,
      });
      if (!result.canceled && result.assets[0]) {
        const a = result.assets[0];
        setPendingImage({
          uri: a.uri,
          base64: a.base64 || '',
          type: a.mimeType?.split('/')[1] || 'jpeg',
        });
      }
    } catch (e) {
      Alert.alert('拍照失败', String(e));
    }
  }, []);

  const pickFile = useCallback(async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: '*/*',
        copyToCacheDirectory: true,
      });
      if (!result.canceled && result.assets[0]) {
        setPickedFileName(result.assets[0].name);
      }
    } catch (e) {
      Alert.alert('选择文件失败', String(e));
    }
  }, []);

  return { pendingImage, pickedFileName, pickImage, takePhoto, pickFile, clearPendingImage, setPendingImage };
}
