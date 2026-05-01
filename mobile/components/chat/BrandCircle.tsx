import React from 'react';
import { View } from 'react-native';
import { useTheme } from '../../hooks/useTheme';

interface Props {
  size: number;
  children: React.ReactNode;
  style?: any;
}

export default function BrandCircle({ size, children, style }: Props) {
  const { c } = useTheme();
  return (
    <View style={[{
      width: size, height: size, borderRadius: size / 2,
      backgroundColor: c.brand,
      alignItems: 'center', justifyContent: 'center',
    }, style]}>
      {children}
    </View>
  );
}
