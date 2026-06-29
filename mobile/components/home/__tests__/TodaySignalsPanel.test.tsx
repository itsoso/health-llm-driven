import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';

import TodaySignalsPanel from '../TodaySignalsPanel';

describe('TodaySignalsPanel', () => {
  it('renders compact signals instead of a full body dashboard', () => {
    const { getByText, getByLabelText, queryByText } = render(
      <TodaySignalsPanel
        sleep={8.3}
        sleepScore={91}
        hrv={59}
        bodyBatteryCurrent={98}
        bodyStats={{ bmi: 22.4, systolic: 120, diastolic: 78, spo2: 96, bodyFatPct: 18.5 }}
        actionSignal="waist_cm"
      />,
    );

    expect(getByText('身体信号')).toBeTruthy();
    expect(getByLabelText('睡眠 8.3h')).toBeTruthy();
    expect(getByLabelText('HRV 59ms')).toBeTruthy();
    expect(getByLabelText('电量 98')).toBeTruthy();
    expect(getByLabelText('BMI 22.4')).toBeTruthy();
    expect(queryByText('/ 8,000')).toBeNull();
  });

  it('uses the action verification signal to pick the fourth body metric route', () => {
    const onSignalPress = jest.fn();
    const { getByLabelText } = render(
      <TodaySignalsPanel
        sleep={null}
        hrv={null}
        bodyBatteryCurrent={null}
        bodyStats={{ bmi: null, systolic: 120, diastolic: 78, spo2: 96, bodyFatPct: null }}
        actionSignal="systolic_bp"
        onSignalPress={onSignalPress}
      />,
    );

    fireEvent.press(getByLabelText('血压 120/78mmHg'));
    expect(onSignalPress).toHaveBeenCalledWith('blood_pressure');
  });
});
