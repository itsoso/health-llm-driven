import React, { useState } from 'react';
import { Image, Text } from 'react-native';
import { JourneyImage, journeyImageSource } from '../../services/journey';
import { journeyStyles as s } from './styles';

export default function JourneyThumbnail({ image, token }: { image: JourneyImage; token: string }) {
  const [failed, setFailed] = useState(false);
  let source;
  try { source = journeyImageSource(image.url, token); } catch { return <Text style={s.error}>照片地址不可用</Text>; }
  if (failed) return <Text style={s.error}>照片加载失败，请取消选图或稍后重试</Text>;
  return <Image source={source} style={{ height: 150, width: '100%', borderRadius: 12 }} resizeMode="contain" onError={() => setFailed(true)} />;
}
