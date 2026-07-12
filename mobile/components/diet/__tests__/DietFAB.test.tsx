import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import DietFAB from '../DietFAB';

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn(),
  ImpactFeedbackStyle: { Light: 'light' },
}));

describe('DietFAB', () => {
  it('exposes a dedicated photo-library action', () => {
    const onLibrary = jest.fn();
    const { getByLabelText, queryByLabelText } = render(
      <DietFAB
        onPhoto={jest.fn()}
        onLibrary={onLibrary}
        onText={jest.fn()}
        onVoice={jest.fn()}
      />,
    );

    expect(queryByLabelText('从相册选择餐食照片')).toBeNull();
    fireEvent.press(getByLabelText('添加饮食记录'));
    fireEvent.press(getByLabelText('从相册选择餐食照片'));

    expect(onLibrary).toHaveBeenCalledTimes(1);
  });
});
