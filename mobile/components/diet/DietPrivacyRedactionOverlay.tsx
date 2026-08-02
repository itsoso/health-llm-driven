import React from 'react';
import { StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { revaColors as C } from '../../constants/revaTheme';
import type { DietShareRedaction, NormalizedPoint } from './dietShareImageEdit';

export type DietPrivacyRedactionOverlayProps = {
  redactions: DietShareRedaction[];
};

function isFinitePoint(point: NormalizedPoint): boolean {
  return Number.isFinite(point.x)
    && Number.isFinite(point.y);
}

function isDrawableRedaction(redaction: DietShareRedaction): boolean {
  if (
    !Array.isArray(redaction.points)
    || redaction.points.length < 2
    || !redaction.points.every(isFinitePoint)
    || !Number.isFinite(redaction.width)
    || redaction.width <= 0
    || redaction.width > 1
  ) return false;

  const first = redaction.points[0];
  return redaction.points.slice(1).some(point => point.x !== first.x || point.y !== first.y);
}

export function dietPrivacyRedactionPath(points: NormalizedPoint[]): string {
  return points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ');
}

export function DietPrivacyRedactionOverlay({ redactions }: DietPrivacyRedactionOverlayProps) {
  const drawable = redactions.filter(isDrawableRedaction);

  return (
    <View
      testID="diet-share-privacy-overlay"
      pointerEvents="none"
      style={styles.overlay}
    >
      <Svg width="100%" height="100%" viewBox="0 0 1 1" preserveAspectRatio="none">
        {drawable.map((redaction, index) => (
          <Path
            key={`${index}:${redaction.points.length}`}
            testID={`diet-share-poster-redaction-${index}`}
            d={dietPrivacyRedactionPath(redaction.points)}
            fill="none"
            stroke={C.ink1}
            strokeOpacity={1}
            strokeWidth={redaction.width}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    overflow: 'hidden',
  },
});
