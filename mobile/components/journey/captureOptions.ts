import { JOURNEY_MAX_HEIGHT, JOURNEY_WIDTH } from '../../services/journey';

/**
 * react-native-view-shot 4.0.3 native semantics differ:
 * iOS RNViewShot.mm uses CGSize points with UIGraphics scale 0 (screen density);
 * Android RNViewShotModule/ViewShot pass integers to Bitmap.createScaledBitmap.
 * Both dimensions must be set: iOS otherwise falls back to view.bounds.
 */
export function journeyCaptureGeometry(layoutHeight: number, platform: string, pixelRatio: number) {
  if (!Number.isFinite(layoutHeight) || layoutHeight < 0) throw new Error('无效的长图高度');
  if (platform === 'ios' && (!Number.isFinite(pixelRatio) || pixelRatio <= 0)) throw new Error('无法确认设备图片比例');
  const outputWidth = JOURNEY_WIDTH * 2;
  const outputHeight = Math.round(layoutHeight * (outputWidth / JOURNEY_WIDTH));
  const nativeDensity = platform === 'ios' ? pixelRatio : 1;
  return {
    outputWidth,
    outputHeight,
    withinBounds: outputHeight > 0 && outputHeight <= JOURNEY_MAX_HEIGHT,
    options: { format: 'png' as const, quality: 1, result: 'tmpfile' as const, width: outputWidth / nativeDensity, height: outputHeight / nativeDensity },
  };
}
