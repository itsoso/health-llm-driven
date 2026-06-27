import { readinessRingGeometry } from '../RevaKit';

describe('readinessRingGeometry', () => {
  it('maps the score to arc offset and tip position', () => {
    const geometry = readinessRingGeometry({ score: 75, size: 100, stroke: 10 });

    expect(geometry.radius).toBe(45);
    expect(geometry.circumference).toBeCloseTo(282.743, 3);
    expect(geometry.fraction).toBe(0.75);
    expect(geometry.renderedFraction).toBe(0.75);
    expect(geometry.strokeDashoffset).toBeCloseTo(70.686, 3);
    expect(geometry.tipX).toBeCloseTo(5, 3);
    expect(geometry.tipY).toBeCloseTo(50, 3);
  });

  it('clamps the score and supports an animated rendered fraction', () => {
    const geometry = readinessRingGeometry({
      score: 120,
      size: 100,
      stroke: 10,
      progress: 0.4,
    });

    expect(geometry.fraction).toBe(1);
    expect(geometry.renderedFraction).toBe(0.4);
    expect(geometry.strokeDashoffset).toBeCloseTo(geometry.circumference * 0.6, 3);
  });
});
