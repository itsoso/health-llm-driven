import React from 'react';
import { View } from 'react-native';
import { colors } from '../../constants/theme';

interface Props {
  size: number;
  children: React.ReactNode;
  style?: any;
}

export default function BrandCircle({ size, children, style }: Props) {
  return (
    <View style={[{
      width: size, height: size, borderRadius: size / 2,
      backgroundColor: colors.brand,
      alignItems: 'center', justifyContent: 'center',
    }, style]}>
      {children}
    </View>
  );
}
