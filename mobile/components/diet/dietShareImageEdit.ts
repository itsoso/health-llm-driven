export type NormalizedPoint = {
  x: number;
  y: number;
};

export type DietShareRedaction = {
  points: NormalizedPoint[];
  width: number;
};

export type DietShareImageEdit = {
  crop: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  rotation: 0 | 90 | 180 | 270;
  redactions: DietShareRedaction[];
};

const MIN_NORMALIZED_SIZE = 0.001;

function clampNormalized(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function isFinitePoint(point: NormalizedPoint): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y);
}

export function initialDietShareImageEdit(): DietShareImageEdit {
  return {
    crop: { x: 0, y: 0, width: 1, height: 1 },
    rotation: 0,
    redactions: [],
  };
}

export function addDietShareRedaction(
  state: DietShareImageEdit,
  redaction: DietShareRedaction,
): DietShareImageEdit {
  if (
    !Array.isArray(redaction.points)
    || redaction.points.length < 2
    || !redaction.points.every(isFinitePoint)
    || !Number.isFinite(redaction.width)
  ) {
    return state;
  }

  const points = redaction.points.map(point => ({
    x: clampNormalized(point.x),
    y: clampNormalized(point.y),
  }));
  const firstPoint = points[0];
  const hasDrawableSegment = points.slice(1).some(point => (
    point.x !== firstPoint.x || point.y !== firstPoint.y
  ));
  if (!hasDrawableSegment) return state;

  return {
    ...state,
    redactions: [
      ...state.redactions,
      {
        points,
        width: Math.min(1, Math.max(MIN_NORMALIZED_SIZE, redaction.width)),
      },
    ],
  };
}

export function updateDietShareCrop(
  state: DietShareImageEdit,
  crop: DietShareImageEdit['crop'],
): DietShareImageEdit {
  if (
    !Number.isFinite(crop.x)
    || !Number.isFinite(crop.y)
    || !Number.isFinite(crop.width)
    || !Number.isFinite(crop.height)
    || crop.width <= 0
    || crop.height <= 0
  ) {
    return state;
  }

  const x = Math.min(clampNormalized(crop.x), 1 - MIN_NORMALIZED_SIZE);
  const y = Math.min(clampNormalized(crop.y), 1 - MIN_NORMALIZED_SIZE);
  const width = Math.min(
    Math.max(crop.width, MIN_NORMALIZED_SIZE),
    1 - x,
  );
  const height = Math.min(
    Math.max(crop.height, MIN_NORMALIZED_SIZE),
    1 - y,
  );

  return {
    ...state,
    crop: { x, y, width, height },
  };
}

export function rotateDietShareImage(state: DietShareImageEdit): DietShareImageEdit {
  const rotation = ((state.rotation + 90) % 360) as DietShareImageEdit['rotation'];
  return { ...state, rotation };
}

export function resetDietShareImageEdit(
  _state?: DietShareImageEdit,
): DietShareImageEdit {
  return initialDietShareImageEdit();
}
