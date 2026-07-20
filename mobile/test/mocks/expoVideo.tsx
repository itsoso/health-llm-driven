import React from 'react';
import { View } from 'react-native';

export const VideoView = React.forwardRef<any, any>((props, ref) => {
  const {
    player: _player,
    nativeControls: _nativeControls,
    contentFit: _contentFit,
    fullscreenOptions: _fullscreenOptions,
    ...viewProps
  } = props;
  return <View {...viewProps} ref={ref} />;
});

VideoView.displayName = 'MockVideoView';

export function useVideoPlayer(
  _source: unknown,
  setup?: (player: Record<string, unknown>) => void,
) {
  const player = {
    loop: false,
    staysActiveInBackground: false,
    showNowPlayingNotification: false,
    play: jest.fn(),
    pause: jest.fn(),
    replace: jest.fn(),
    release: jest.fn(),
  };
  setup?.(player);
  return player;
}
