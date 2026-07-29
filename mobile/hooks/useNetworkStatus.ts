import { useEffect, useState } from 'react';
import NetInfo from '@react-native-community/netinfo';
import { resolveNetworkOnlineState } from '../utils/networkReachability';

export function useNetworkStatus() {
  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    return NetInfo.addEventListener((state) => {
      setIsOnline(current => resolveNetworkOnlineState(current, state));
    });
  }, []);

  return { isOnline };
}
