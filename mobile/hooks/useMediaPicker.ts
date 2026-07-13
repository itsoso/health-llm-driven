import { useState, useCallback, useRef } from 'react';
import { Alert } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import { deleteDraftImage, materializeDraftImages } from '../services/chatDraftStorage';

const MAX_IMAGES = 9;

export interface PendingImage {
  uri: string;
  base64: string;
  type: string;
  draftCreatedAt?: number;
}

export function useMediaPicker() {
  const [pendingImages, setPendingImagesState] = useState<PendingImage[]>([]);
  const pendingImagesRef = useRef<PendingImage[]>([]);
  const [pickedFileName, setPickedFileName] = useState<string | null>(null);

  pendingImagesRef.current = pendingImages;

  const setPendingImages = useCallback((images: PendingImage[]) => {
    const next = images.slice(0, MAX_IMAGES);
    pendingImagesRef.current = next;
    setPendingImagesState(next);
  }, []);

  const addImages = useCallback(async (newImages: PendingImage[]) => {
    const remaining = MAX_IMAGES - pendingImagesRef.current.length;
    if (remaining <= 0) {
      Alert.alert('已达上限', `最多选择 ${MAX_IMAGES} 张图片`);
      return [];
    }
    if (newImages.length > remaining) {
      Alert.alert('最多选择 9 张', `已保留前 ${MAX_IMAGES} 张`);
    }
    const durableImages = await materializeDraftImages(newImages.slice(0, remaining));
    setPendingImages([...pendingImagesRef.current, ...durableImages]);
    return durableImages;
  }, [setPendingImages]);

  const removeImage = useCallback(async (index: number) => {
    const removed = pendingImagesRef.current[index];
    setPendingImages(pendingImagesRef.current.filter((_, i) => i !== index));
    if (removed) await deleteDraftImage(removed);
  }, [setPendingImages]);

  const clearImages = useCallback(async () => {
    const removed = pendingImagesRef.current;
    setPendingImages([]);
    await Promise.all(removed.map(image => deleteDraftImage(image)));
  }, [setPendingImages]);

  // 服务端已持久化请求后，当前消息气泡仍引用这些本地文件。这里只释放输入框状态，
  // 文件由草稿目录的过期清理回收；显式移除/取消仍走 clearImages 并立即删除。
  const releaseImagesAfterSend = useCallback(() => {
    setPendingImages([]);
  }, [setPendingImages]);

  const setPendingImage = useCallback(async (img: PendingImage | null) => {
    if (!img) {
      await clearImages();
      return;
    }
    const [durable] = await materializeDraftImages([img]);
    const removed = pendingImagesRef.current;
    setPendingImages(durable ? [durable] : []);
    await Promise.all(removed.map(image => deleteDraftImage(image)));
  }, [clearImages, setPendingImages]);

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
        await addImages(picked);
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
        await addImages([{
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

  return {
    pendingImage, setPendingImage,
    pendingImages, setPendingImages, addImages, removeImage, clearImages, releaseImagesAfterSend,
    pickedFileName, pickImage, takePhoto, pickFile,
  };
}
