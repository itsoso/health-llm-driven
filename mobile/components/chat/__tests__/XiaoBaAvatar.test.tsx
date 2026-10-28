import React from 'react';
import { Image } from 'react-native';
import { render } from '@testing-library/react-native';
import XiaoBaAvatar from '../XiaoBaAvatar';

describe('XiaoBaAvatar brand identity', () => {
  it.each([true, false])('uses the launcher artwork with compact=%s', (compact) => {
    const screen = render(<XiaoBaAvatar compact={compact} size={28} />);
    expect(screen.getByLabelText('小气候形象')).toBeTruthy();
    expect(screen.UNSAFE_getByType(Image).props.source).toBe(
      require('../../../assets/images/icon.png'),
    );
  });
});
