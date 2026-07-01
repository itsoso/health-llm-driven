export function isSafeInternalRoute(route: unknown): route is string {
  if (typeof route !== 'string') return false;
  if (!route.startsWith('/')) return false;
  if (route.startsWith('//')) return false;
  if (/[\u0000-\u001f\u007f]/.test(route)) return false;
  return true;
}
