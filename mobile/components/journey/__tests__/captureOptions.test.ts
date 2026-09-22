jest.mock('../../../services/api', () => ({ __esModule: true, default: {}, BASE_URL: 'https://health.executor.life/api' }));
jest.mock('expo-location', () => ({}));
import { journeyCaptureGeometry } from '../captureOptions';

describe('native journey PNG dimensions', () => {
  it.each([2, 3])('converts target pixels into iOS points at %sx while preserving aspect ratio', density => {
    const capture = journeyCaptureGeometry(762, 'ios', density);
    expect(capture.outputWidth).toBe(720);
    expect(capture.outputHeight).toBe(1524);
    expect(capture.options).toEqual({ format: 'png', quality: 1, result: 'tmpfile', width: 720 / density, height: 1524 / density });
    expect(capture.options.width / capture.options.height).toBeCloseTo(360 / 762);
    expect(capture.withinBounds).toBe(true);
  });
  it.each([2, 3])('passes Android native bitmap dimensions in pixels, not points, at density %s', density => {
    expect(journeyCaptureGeometry(762, 'android', density).options).toEqual({ format: 'png', quality: 1, result: 'tmpfile', width: 720, height: 1524 });
  });
  it('checks exact rounded output pixels, not iOS native points', () => {
    expect(journeyCaptureGeometry(8000, 'ios', 3).withinBounds).toBe(true);
    const over = journeyCaptureGeometry(8000.3, 'ios', 3);
    expect(over.outputHeight).toBe(16001);
    expect(over.withinBounds).toBe(false);
    expect(journeyCaptureGeometry(0, 'ios', 3).withinBounds).toBe(false);
  });
  it.each([0, -1, NaN, Infinity])('fails closed on invalid iOS density %s', density => {
    expect(() => journeyCaptureGeometry(762, 'ios', density)).toThrow();
  });
});
