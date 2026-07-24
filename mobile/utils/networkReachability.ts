export type NetworkReachabilityState = {
  isConnected?: boolean | null;
  isInternetReachable?: boolean | null;
};

export function isNetworkStateUnavailable(state: NetworkReachabilityState): boolean {
  return state.isConnected === false || state.isInternetReachable === false;
}

export function resolveNetworkOnlineState(
  current: boolean,
  state: NetworkReachabilityState,
): boolean {
  if (isNetworkStateUnavailable(state)) return false;
  if (state.isConnected === true && state.isInternetReachable === true) return true;
  if (state.isConnected === true && state.isInternetReachable === undefined) return true;
  return current;
}
