import {
  addDietShareRedaction,
  initialDietShareImageEdit,
  resetDietShareImageEdit,
  rotateDietShareImage,
  updateDietShareCrop,
} from '../dietShareImageEdit';

describe('dietShareImageEdit', () => {
  it('starts with an identity crop, zero rotation, and no redactions', () => {
    expect(initialDietShareImageEdit()).toEqual({
      crop: { x: 0, y: 0, width: 1, height: 1 },
      rotation: 0,
      redactions: [],
    });
  });

  it('adds a normalized redaction without mutating the previous state', () => {
    const initial = initialDietShareImageEdit();

    const edited = addDietShareRedaction(initial, {
      points: [
        { x: -0.1, y: 0.4 },
        { x: 1.2, y: 0.8 },
      ],
      width: 0.06,
    });

    expect(edited).not.toBe(initial);
    expect(edited.redactions).toEqual([{
      points: [
        { x: 0, y: 0.4 },
        { x: 1, y: 0.8 },
      ],
      width: 0.06,
    }]);
    expect(initial.redactions).toEqual([]);
  });

  it('clamps redaction width to a drawable normalized range', () => {
    const initial = initialDietShareImageEdit();
    const points = [{ x: 0.1, y: 0.2 }, { x: 0.8, y: 0.9 }];

    const tooThin = addDietShareRedaction(initial, { points, width: 0.0001 });
    const tooWide = addDietShareRedaction(initial, { points, width: 2 });

    expect(tooThin.redactions[0]?.width).toBeGreaterThan(0);
    expect(tooThin.redactions[0]?.width).toBeLessThanOrEqual(1);
    expect(tooWide.redactions[0]?.width).toBe(1);
  });

  it('rejects undrawable or non-finite redaction strokes by returning the same state', () => {
    const initial = initialDietShareImageEdit();

    expect(addDietShareRedaction(initial, { points: [], width: 0.06 })).toBe(initial);
    expect(addDietShareRedaction(initial, {
      points: [{ x: 0.1, y: 0.2 }],
      width: 0.06,
    })).toBe(initial);
    expect(addDietShareRedaction(initial, {
      points: [{ x: 0.1, y: 0.2 }, { x: Number.NaN, y: 0.3 }],
      width: 0.06,
    })).toBe(initial);
    const drawablePoints = [{ x: 0.1, y: 0.2 }, { x: 0.3, y: 0.4 }];
    [0, -0.01, Number.NaN, Number.POSITIVE_INFINITY].forEach(width => {
      expect(addDietShareRedaction(initial, {
        points: drawablePoints,
        width,
      })).toBe(initial);
    });
  });

  it('clamps crop coordinates while preserving positive in-bounds dimensions immutably', () => {
    const initial = initialDietShareImageEdit();

    const edited = updateDietShareCrop(initial, {
      x: -0.25,
      y: 0.8,
      width: 1.5,
      height: 0.6,
    });

    expect(edited).not.toBe(initial);
    expect(edited.crop.x).toBe(0);
    expect(edited.crop.y).toBe(0.8);
    expect(edited.crop.width).toBe(1);
    expect(edited.crop.height).toBeCloseTo(0.2);
    expect(initial.crop).toEqual({ x: 0, y: 0, width: 1, height: 1 });
  });

  it('rejects non-finite and non-positive crop dimensions', () => {
    const initial = initialDietShareImageEdit();

    expect(updateDietShareCrop(initial, {
      x: Number.NaN,
      y: 0,
      width: 0.5,
      height: 0.5,
    })).toBe(initial);
    expect(updateDietShareCrop(initial, {
      x: 0,
      y: 0,
      width: 0,
      height: 0.5,
    })).toBe(initial);
  });

  it('rotates clockwise in 90 degree steps and wraps to zero', () => {
    const initial = initialDietShareImageEdit();
    const source = { width: 1600, height: 1200 };
    const at90 = rotateDietShareImage(initial, source);
    const at180 = rotateDietShareImage(at90, source);
    const at270 = rotateDietShareImage(at180, source);
    const atZero = rotateDietShareImage(at270, source);

    expect([at90.rotation, at180.rotation, at270.rotation, atZero.rotation]).toEqual([
      90,
      180,
      270,
      0,
    ]);
    expect(initial.rotation).toBe(0);
  });

  it('rotates a non-centre crop and privacy stroke with the photo', () => {
    const initial = {
      ...initialDietShareImageEdit(),
      crop: { x: 0.1, y: 0.2, width: 0.4, height: 0.4 },
      redactions: [{
        points: [{ x: 0.1, y: 0.2 }, { x: 0.25, y: 0.35 }],
        width: 0.06,
      }],
    };

    const rotated = rotateDietShareImage(initial, { width: 1600, height: 1200 });

    expect(rotated).toEqual({
      crop: { x: 0.4, y: 0.1875, width: 0.4, height: 0.4 },
      rotation: 90,
      redactions: [{
        points: [{ x: 0.8, y: 0.275 }, { x: 0.65, y: 0.359375 }],
        width: 0.06,
      }],
    });
    expect(initial.crop).toEqual({ x: 0.1, y: 0.2, width: 0.4, height: 0.4 });
    expect(initial.redactions[0]?.points[0]).toEqual({ x: 0.1, y: 0.2 });
  });

  it('maps a visible point through source pixels rather than a square shortcut', () => {
    const initial = {
      ...initialDietShareImageEdit(),
      redactions: [{
        points: [{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.2 }],
        width: 0.08,
      }],
    };

    const result = rotateDietShareImage(initial, { width: 1600, height: 1200 });

    expect(result.crop).toEqual({ x: 0, y: 0, width: 1, height: 1 });
    expect(result.redactions[0]?.points[0]?.x).toBeCloseTo(0.9);
    expect(result.redactions[0]?.points[0]?.y).toBeCloseTo(0.275);
  });

  it('reset restores a fresh identity state exactly', () => {
    const edited = addDietShareRedaction(
      rotateDietShareImage(updateDietShareCrop(initialDietShareImageEdit(), {
        x: 0.1,
        y: 0.2,
        width: 0.7,
        height: 0.6,
      }), { width: 1600, height: 1200 }),
      {
        points: [{ x: 0.2, y: 0.2 }, { x: 0.8, y: 0.8 }],
        width: 0.06,
      },
    );

    expect(resetDietShareImageEdit(edited)).toEqual(initialDietShareImageEdit());
  });
});
