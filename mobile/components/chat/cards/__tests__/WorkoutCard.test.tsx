import React from 'react';
import { render } from '@testing-library/react-native';
import { Ionicons } from '@expo/vector-icons';
import { StyleSheet } from 'react-native';
import { WorkoutCardView } from '../WorkoutCard';
import { revaColors as C } from '../../../../constants/revaTheme';

jest.mock('react-native/Libraries/Utilities/useColorScheme', () => ({
  __esModule: true,
  default: () => 'light',
}));

describe('WorkoutCardView visual hierarchy', () => {
  it('uses the Reva surface and one restrained metric color', () => {
    const tree = render(
      <WorkoutCardView
        activity_type="基础训练"
        workout_date="2026-06-22"
        duration_min={7}
        distance_km={0.68}
        calories={44}
        avg_hr={106}
        avg_pace={'10\'43"/km'}
      />,
    );

    const root = tree.toJSON();
    expect(root).not.toBeNull();
    expect(StyleSheet.flatten((root as any).props.style).backgroundColor).toBe(C.surface2);

    const headerIcon = tree.UNSAFE_getAllByType(Ionicons as any)[0];
    expect(headerIcon.props.color).toBe(C.green500);

    ['7min', '0.68km', '44kcal', '106bpm', '10\'43"/km'].forEach((value) => {
      expect(StyleSheet.flatten(tree.getByText(value).props.style).color).toBe(C.ink1);
    });
  });
});
