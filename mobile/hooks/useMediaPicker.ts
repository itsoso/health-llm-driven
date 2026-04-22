import { useState, useCallback } from 'react';
import { Alert } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';

const MAX_IMAGES = 9;

export interface PendingImage {
  uri: string;
  base64: string;
  type: string;
}

export function useMediaPicker() {
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [pickedFileName, setPickedFileName] = useState<string | null>(null);

  const addImages = useCallback((newImages: PendingImage[]) => {
    setPendingImages(prev => {
      const combined = [...prev, ...newImages];
      if (combined.length > MAX_IMAGES) {
        Alert.alert('最多选择 9 张', `已保留前 ${MAX_IMAGES} 张`);
        return combined.slice(0, MAX_IMAGES);
      }
      return combined;
    });
  }, []);

  const removeImage = useCallback((index: number) => {
    setPendingImages(prev => prev.filter((_, i) => i !== index));
  }, []);

  const clearImages = useCallback(() => setPendingImages([]), []);

  const pickImage = useCallback(async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相册权限', '请在系统设置中允许 HealthPilot 访问相册');
        return;
      }
      const remaining = MAX_IMAGES - (pendingImages?.length || 0);
      if (remaining <= 0) {
        Alert.alert('已达上限', `最多选择 ${MAX_IMAGES} 张图片`);
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        base64: true,
        quality: 0.8,
        allowsMultipleSelection: true,
        selectionLimit: remaining,
      });
      if (!result.canceled && result.assets.length > 0) {
        const picked: PendingImage[] = result.assets.map(a => ({
          uri: a.uri,
          base64: a.base64 || '',
          type: a.mimeType?.split('/')[1] || 'jpeg',
        }));
        addImages(picked);
      }
    } catch (e) {
      Alert.alert('选择图片失败', String(e));
    }
  }, [pendingImages?.length, addImages]);

  const takePhoto = useCallback(async () => {
    try {
      if ((pendingImages?.length || 0) >= MAX_IMAGES) {
        Alert.alert('已达上限', `最多选择 ${MAX_IMAGES} 张图片`);
        return;
      }
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
        addImages([{
          uri: a.uri,
          base64: a.base64 || '',
          type: a.mimeType?.split('/')[1] || 'jpeg',
        }]);
      }
    } catch (e) {
      Alert.alert('拍照失败', String(e));
    }
  }, [pendingImages?.length, addImages]);

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

  // Backward-compatible single-image API
  const pendingImage = pendingImages.length > 0 ? pendingImages[0] : null;
  const setPendingImage = useCallback((img: PendingImage | null) => {
    setPendingImages(img ? [img] : []);
  }, []);

  return {
    pendingImage, setPendingImage,
    pendingImages, setPendingImages, addImages, removeImage, clearImages,
    pickedFileName, pickImage, takePhoto, pickFile,
  };
}
