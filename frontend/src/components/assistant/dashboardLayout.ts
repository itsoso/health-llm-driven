export type AssistantLayoutDevice = 'web' | 'mobile';

export interface AssistantDashboardDeviceLayout {
  order: string[];
  hidden: string[];
}

export const DASHBOARD_CARD_IDS = [
  'hero',
  'safety',
  'consultations',
  'action_cards',
  'specialists',
  'alerts',
  'data_grid',
  'strength',
  'workout_supplement',
  'supplement_guide',
  'activity',
  'exercise',
  'trends',
  'quick_asks',
] as const;

const VALID_CARD_IDS = new Set<string>(DASHBOARD_CARD_IDS);

export function getDefaultDashboardLayout(): AssistantDashboardDeviceLayout {
  return {
    order: [...DASHBOARD_CARD_IDS],
    hidden: [],
  };
}

export function normalizeDashboardLayout(input?: Partial<AssistantDashboardDeviceLayout> | null): AssistantDashboardDeviceLayout {
  const fallback = getDefaultDashboardLayout();
  const inputOrder = Array.isArray(input?.order) ? input!.order : [];
  const inputHidden = Array.isArray(input?.hidden) ? input!.hidden : [];

  const order: string[] = [];
  for (const id of inputOrder) {
    if (VALID_CARD_IDS.has(id) && !order.includes(id)) {
      order.push(id);
    }
  }
  for (const id of fallback.order) {
    if (!order.includes(id)) {
      order.push(id);
    }
  }

  const hidden = inputHidden.filter((id, index) => VALID_CARD_IDS.has(id) && inputHidden.indexOf(id) === index);

  return { order, hidden };
}

export function detectAssistantLayoutDevice(): AssistantLayoutDevice {
  if (typeof window === 'undefined') {
    return 'web';
  }

  const userAgent = window.navigator.userAgent || '';
  const isMobileUserAgent = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(userAgent);
  const isCapacitor = !!(window as Window & { Capacitor?: unknown }).Capacitor;

  return isMobileUserAgent || isCapacitor ? 'mobile' : 'web';
}

export function getWelcomeContentBottomPaddingClass({
  isMobile,
  hasFooterControls,
}: {
  isMobile: boolean;
  hasFooterControls: boolean;
}): string {
  if (isMobile && hasFooterControls) {
    return 'pb-72';
  }
  if (isMobile) {
    return 'pb-56';
  }
  return 'pb-44';
}
