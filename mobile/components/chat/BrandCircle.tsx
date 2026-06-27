import React from 'react';
import { View } from 'react-native';
import { revaColors as C } from '../../constants/revaTheme';

interface Props {
  size: number;
  children: React.ReactNode;
  style?: any;
}

export default function BrandCircle({ size, children, style }: Props) {
  return (
    <View style={[{
      width: size, height: size, borderRadius: size / 2,
      backgroundColor: C.green500,
      alignItems: 'center', justifyContent: 'center',
    }, style]}>
      {children}
    </View>
  );
}
