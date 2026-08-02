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
const POSTER_ASPECT_RATIO = 3 / 4;

export type DietShareImageSize = {
  width: number;
  height: number;
};

function clampNormalized(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function isFinitePoint(point: NormalizedPoint): boolean {
  return Number.isFinite(point.x) && Number.isFinite(point.y);
}

function validImageSize(size: DietShareImageSize): boolean {
  return Number.isFinite(size.width)
    && Number.isFinite(size.height)
    && size.width > 0
    && size.height > 0;
}

export function effectiveDietShareImageSize(
  source: DietShareImageSize,
  rotation: DietShareImageEdit['rotation'],
): DietShareImageSize {
  return rotation === 90 || rotation === 270
    ? { width: source.height, height: source.width }
    : source;
}

export function baseDietShareCropForPoster(source: DietShareImageSize): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  const sourceRatio = source.width / source.height;
  if (sourceRatio > POSTER_ASPECT_RATIO) {
    const width = source.height * POSTER_ASPECT_RATIO;
    return { x: (source.width - width) / 2, y: 0, width, height: source.height };
  }
  const height = source.width / POSTER_ASPECT_RATIO;
  return { x: 0, y: (source.height - height) / 2, width: source.width, height };
}

function visibleDietShareCrop(
  effectiveSource: DietShareImageSize,
  crop: DietShareImageEdit['crop'],
): { x: number; y: number; width: number; height: number; size: number } {
  const base = baseDietShareCropForPoster(effectiveSource);
  const size = Math.max(
    MIN_NORMALIZED_SIZE,
    Math.min(1, crop.width, crop.height),
  );
  const x = Math.min(1 - size, Math.max(0, crop.x));
  const y = Math.min(1 - size, Math.max(0, crop.y));
  return {
    x: base.x + x * base.width,
    y: base.y + y * base.height,
    width: size * base.width,
    height: size * base.height,
    size,
  };
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
    || redaction.width <= 0
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

export function rotateDietShareImage(
  state: DietShareImageEdit,
  source: DietShareImageSize,
): DietShareImageEdit {
  if (!validImageSize(source)) return state;
  const rotation = ((state.rotation + 90) % 360) as DietShareImageEdit['rotation'];
  const oldEffective = effectiveDietShareImageSize(source, state.rotation);
  const nextEffective = effectiveDietShareImageSize(source, rotation);
  const oldVisible = visibleDietShareCrop(oldEffective, state.crop);
  const nextBase = baseDietShareCropForPoster(nextEffective);
  const nextWidth = nextBase.width * oldVisible.size;
  const nextHeight = nextBase.height * oldVisible.size;
  const oldCenterX = oldVisible.x + oldVisible.width / 2;
  const oldCenterY = oldVisible.y + oldVisible.height / 2;
  const rotatedCenterX = oldEffective.height - oldCenterY;
  const rotatedCenterY = oldCenterX;
  const nextX = Math.min(
    nextBase.x + nextBase.width - nextWidth,
    Math.max(nextBase.x, rotatedCenterX - nextWidth / 2),
  );
  const nextY = Math.min(
    nextBase.y + nextBase.height - nextHeight,
    Math.max(nextBase.y, rotatedCenterY - nextHeight / 2),
  );
  const crop = {
    x: clampNormalized((nextX - nextBase.x) / nextBase.width),
    y: clampNormalized((nextY - nextBase.y) / nextBase.height),
    width: oldVisible.size,
    height: oldVisible.size,
  };
  const redactions = state.redactions.map(redaction => ({
    ...redaction,
    points: redaction.points.map(point => {
      const sourceX = oldVisible.x + point.x * oldVisible.width;
      const sourceY = oldVisible.y + point.y * oldVisible.height;
      const rotatedX = oldEffective.height - sourceY;
      const rotatedY = sourceX;
      return {
        // Keep finite canonical coordinates outside the current viewport.
        // The SVG clips them for display; retaining them makes later rotations lossless.
        x: (rotatedX - nextX) / nextWidth,
        y: (rotatedY - nextY) / nextHeight,
      };
    }),
  }));
  return { ...state, crop, rotation, redactions };
}

export function resetDietShareImageEdit(
  _state?: DietShareImageEdit,
): DietShareImageEdit {
  return initialDietShareImageEdit();
}
