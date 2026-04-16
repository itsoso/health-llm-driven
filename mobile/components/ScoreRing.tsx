import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Circle } from 'react-native-svg';

interface ScoreRingProps {
  score: number;
  maxScore?: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  label?: string;
}

export default function ScoreRing({
  score,
  maxScore = 100,
  size = 120,
  strokeWidth = 10,
  color = '#34C759',
  label = '健康评分',
}: ScoreRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(score / maxScore, 1);
  const strokeDashoffset = circumference * (1 - pct);
  const center = size / 2;

  const ringColor =
    score >= 80 ? '#34C759' : score >= 60 ? '#FF9500' : '#FF3B30';
  const finalColor = color !== '#34C759' ? color : ringColor;

  return (
    <View style={styles.container}>
      <Svg width={size} height={size}>
        <Circle
          cx={center}
          cy={center}
          r={radius}
          stroke="#E5E5EA"
          strokeWidth={strokeWidth}
          fill="transparent"
        />
        <Circle
          cx={center}
          cy={center}
          r={radius}
          stroke={finalColor}
          strokeWidth={strokeWidth}
          fill="transparent"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          rotation="-90"
          origin={`${center}, ${center}`}
        />
      </Svg>
      <View style={[styles.labelWrap, { width: size, height: size }]}>
        <Text style={[styles.scoreText, { color: finalColor }]}>
          {Math.round(score)}
        </Text>
        <Text style={styles.labelText}>{label}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  labelWrap: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
  },
  scoreText: {
    fontSize: 28,
    fontWeight: '700',
  },
  labelText: {
    fontSize: 11,
    color: '#8E8E93',
    marginTop: 2,
  },
});
