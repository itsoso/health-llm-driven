import { useState, useCallback } from 'react';
import { Alert } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
// 只引类型(编译期擦除,不产生 runtime require)—— 运行时用下面的 guarded require 探测。
import type { Action } from 'expo-image-manipulator';

const MAX_IMAGES = 9;

// 拍照记餐主链路上,一张 12MP 原图 base64 约 3-5MB,9 张能到 30-45MB。
// 同步 JSON.stringify 会卡死 JS 线程数秒并触发 413/超时。
// 发送前把最长边压到 1568px(Claude vision 甜点)并以 JPEG q0.7 重编码,
// 让 manipulator 直接产出 base64,payload 缩小 10-20 倍。
const MAX_EDGE = 1568;
const COMPRESS = 0.7;

// OTA 安全:expo-image-manipulator 的 NativeImageManipulatorModule 在 import 时
// eager 调 requireNativeModule('ExpoImageManipulator')。若这份 JS 通过 OTA 落到
// 一个 package.json 里还没有该依赖的旧二进制(native 侧缺失),静态 import 会在
// bundle 加载时抛错,直接把整个 picker/chat 屏 brick 掉。
// 所以改成 guarded require 探测一次(可用性对同一个二进制是静态的,探一次即定)。
// 探测失败(旧二进制)→ 走无压缩的 picker base64 兜底,保留旧行为。
let Manipulator: typeof import('expo-image-manipulator') | null = null;
try {
  Manipulator = require('expo-image-manipulator');
} catch {
  Manipulator = null;
  // eslint-disable-next-line no-console
  console.warn('[useMediaPicker] image-manipulator unavailable (old binary) — sending uncompressed');
}

export interface PendingImage {
  uri: string;
  base64: string;
  type: string;
}

// 旧二进制兜底路径用:从 asset 元信息推断真实图片格式(与历史行为一致)。
function normalizeImageType(asset: ImagePicker.ImagePickerAsset): string {
  const fromMime = asset.mimeType?.split('/')[1];
  const fromName = asset.fileName?.split('.').pop();
  const fromUri = asset.uri?.split(/[?#]/)[0]?.split('.').pop();
  const raw = (fromMime || fromName || fromUri || 'jpeg').toLowerCase();
  return raw === 'jpg' ? 'jpeg' : raw;
}

/**
 * 把单张 asset 变成待发送图。
 * - 新二进制(manipulator 可用):缩放(最长边 → MAX_EDGE,保持比例、绝不放大)
 *   + JPEG 重压缩,直接拿 base64。
 * - 旧二进制(manipulator 缺失):用 picker 内联 base64,无压缩。
 * 两条路径都 fail-loud:base64 空 → 返回 null(调用方排除该图并提示),绝不下发空图。
 */
async function toPendingImage(asset: ImagePicker.ImagePickerAsset): Promise<PendingImage | null> {
  if (!asset.uri) return null;

  const M = Manipulator;
  if (!M) {
    // 旧二进制兜底:picker 已按 base64:true 内联,无压缩直接用。
    const base64 = typeof asset.base64 === 'string' ? asset.base64 : '';
    if (!base64) return null;
    return { uri: asset.uri, base64, type: normalizeImageType(asset) };
  }

  const width = asset.width ?? 0;
  const height = asset.height ?? 0;
  const longestEdge = Math.max(width, height);
  const actions: Action[] = [];
  if (longestEdge > MAX_EDGE) {
    actions.push(width >= height ? { resize: { width: MAX_EDGE } } : { resize: { height: MAX_EDGE } });
  }
  const result = await M.manipulateAsync(asset.uri, actions, {
    compress: COMPRESS,
    format: M.SaveFormat.JPEG,
    base64: true,
  });
  if (!result.base64) return null;
  return {
    uri: result.uri,
    base64: result.base64,
    type: 'jpeg',
  };
}

/**
 * 绝不抛错:单张处理失败(manipulator 抛异常)解析为 null,
 * 一张坏图不拖垮整批(调用方数 null 提示用户已跳过)。
 */
async function toPendingImageSafe(asset: ImagePicker.ImagePickerAsset): Promise<PendingImage | null> {
  try {
    return await toPendingImage(asset);
  } catch {
    return null;
  }
}

function warnSkipped(count: number) {
  if (count <= 0) return;
  Alert.alert('该图片无法读取，已跳过', count > 1 ? `共跳过 ${count} 张` : '请重试或换一张图片');
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
        allowsMultipleSelection: true,
        selectionLimit: remaining,
        // 新二进制:由 manipulator 独占编码,不向 picker 要 base64/quality;
        // 旧二进制:回退到 picker 内联 base64 + 原 quality。
        base64: !Manipulator,
        ...(Manipulator ? null : { quality: 0.8 }),
      });
      if (!result.canceled && result.assets.length > 0) {
        const processed = await Promise.all(result.assets.map(toPendingImageSafe));
        const picked = processed.filter((img): img is PendingImage => !!img);
        warnSkipped(result.assets.length - picked.length);
        if (picked.length === 0) return;
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
        mediaTypes: ['images'],
        base64: !Manipulator,
        ...(Manipulator ? null : { quality: 0.8 }),
      });
      if (!result.canceled && result.assets[0]) {
        const image = await toPendingImageSafe(result.assets[0]);
        if (!image) {
          warnSkipped(1);
          return;
        }
        addImages([image]);
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
