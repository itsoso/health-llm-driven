import { useState, useCallback, useRef } from 'react';
import { Alert } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import { deleteDraftImage, materializeDraftImages } from '../services/chatDraftStorage';
import {
  cleanupPreparedUploadImages,
  imagePickerEncodingOptions,
  prepareImageForUploadSafe,
} from '../utils/imageUpload';
import type { PreparedUploadImage } from '../utils/imageUpload';

const DEFAULT_MAX_IMAGES = 9;

function imageLimit(value?: number): number {
  if (!Number.isFinite(value)) return DEFAULT_MAX_IMAGES;
  return Math.max(1, Math.min(DEFAULT_MAX_IMAGES, Math.floor(Number(value))));
}

function imageLimitAlert(maxImages: number, truncated = false): void {
  const mealCapture = maxImages === 3;
  Alert.alert(
    mealCapture ? '本餐最多 3 张照片' : '已达上限',
    truncated
      ? `已保留前 ${maxImages} 张，请发送后再继续补充`
      : `最多选择 ${maxImages} 张图片`,
  );
}

export interface PendingImage {
  uri: string;
  base64: string;
  type: string;
  draftCreatedAt?: number;
}

function warnSkipped(count: number) {
  if (count <= 0) return;
  Alert.alert('该图片无法读取，已跳过', count > 1 ? `共跳过 ${count} 张` : '请重试或换一张图片');
}

function toPendingImage(image: PreparedUploadImage): PendingImage {
  return { uri: image.uri, base64: image.base64, type: image.type };
}

export function useMediaPicker() {
  const [pendingImages, setPendingImagesState] = useState<PendingImage[]>([]);
  const pendingImagesRef = useRef<PendingImage[]>([]);
  const [pickedFileName, setPickedFileName] = useState<string | null>(null);

  pendingImagesRef.current = pendingImages;

  const setPendingImages = useCallback((images: PendingImage[], requestedLimit = DEFAULT_MAX_IMAGES) => {
    const next = images.slice(0, imageLimit(requestedLimit));
    pendingImagesRef.current = next;
    setPendingImagesState(next);
  }, []);

  const addImages = useCallback(async (
    newImages: PendingImage[],
    requestedLimit = DEFAULT_MAX_IMAGES,
  ) => {
    const maxImages = imageLimit(requestedLimit);
    const remaining = maxImages - pendingImagesRef.current.length;
    if (remaining <= 0) {
      imageLimitAlert(maxImages);
      return [];
    }
    if (newImages.length > remaining) {
      imageLimitAlert(maxImages, true);
    }
    const durableImages = await materializeDraftImages(newImages.slice(0, remaining));
    setPendingImages([...pendingImagesRef.current, ...durableImages], maxImages);
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

  const releaseImagesAfterSend = useCallback(async () => {
    const accepted = pendingImagesRef.current;
    setPendingImages([]);
    await Promise.all(accepted.map(image => deleteDraftImage(image)));
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

  const pickImage = useCallback(async (requestedLimit = DEFAULT_MAX_IMAGES) => {
    try {
      const maxImages = imageLimit(requestedLimit);
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相册权限', '请在系统设置中允许小巴访问相册');
        return;
      }
      const remaining = maxImages - pendingImagesRef.current.length;
      if (remaining <= 0) {
        imageLimitAlert(maxImages);
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsMultipleSelection: true,
        selectionLimit: remaining,
        ...imagePickerEncodingOptions(),
      });
      if (!result.canceled && result.assets.length > 0) {
        const processed = await Promise.all(result.assets.map(prepareImageForUploadSafe));
        const picked = processed.filter((img): img is PreparedUploadImage => !!img);
        warnSkipped(result.assets.length - picked.length);
        if (picked.length === 0) return;
        try {
          await addImages(picked.map(toPendingImage), maxImages);
        } finally {
          await cleanupPreparedUploadImages(picked);
        }
      }
    } catch (e) {
      Alert.alert('选择图片失败', String(e));
    }
  }, [addImages]);

  const takePhoto = useCallback(async (
    requestedLimit = DEFAULT_MAX_IMAGES,
  ): Promise<PendingImage[]> => {
    try {
      const maxImages = imageLimit(requestedLimit);
      if (pendingImagesRef.current.length >= maxImages) {
        imageLimitAlert(maxImages);
        return [];
      }
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相机权限', '请在系统设置中允许小巴使用相机');
        return [];
      }
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ['images'],
        ...imagePickerEncodingOptions(),
      });
      if (!result.canceled && result.assets[0]) {
        const image = await prepareImageForUploadSafe(result.assets[0]);
        if (!image) {
          warnSkipped(1);
          return [];
        }
        try {
          return await addImages([toPendingImage(image)], maxImages);
        } finally {
          await cleanupPreparedUploadImages([image]);
        }
      }
      return [];
    } catch (e) {
      Alert.alert('拍照失败', String(e));
      return [];
    }
  }, [addImages]);

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
