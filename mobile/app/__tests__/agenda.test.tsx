/* eslint-disable import/first */
import React from 'react';
import { ActionSheetIOS, Alert, Platform } from 'react-native';
import { fireEvent, render } from '@testing-library/react-native';

import type { AgendaToday } from '../../services/agenda';

const mockBack = jest.fn();
const mockNavigate = jest.fn();
const mockMutate = jest.fn();
const mockSnoozeMutate = jest.fn();
const mockResumeMutate = jest.fn();
const mockPushChatWithContext = jest.fn();
const mockToast = jest.fn();
const mockShowUndoable = jest.fn();
let mockCanGoBack = true;
let mockAgendaData: AgendaToday;
let mockCompleteState: {
  isPending: boolean;
  variables?: { source: { object_type: string; object_id: number | string; slot?: string } };
} = { isPending: false };
let mockSnoozeState: {
  isPending: boolean;
  variables?: { source: { object_type: string; object_id: number | string; slot?: string } };
} = { isPending: false };
let mockResumeState: {
  isPending: boolean;
  variables?: { source: { object_type: string; object_id: number | string; slot?: string } };
} = { isPending: false };

const agendaData: AgendaToday = {
  agenda_date: '2026-07-20',
  count: 4,
  items: [
    {
      type: 'medication',
      title: '晨间用药',
      status: 'pending',
      priority: 90,
      time_window: 'morning',
      source: { object_type: 'health_protocol', object_id: 2 },
    },
    {
      type: 'advisory',
      title: '优质蛋白有助修复',
      status: 'active',
      priority: 80,
      time_window: 'anytime',
      source: { object_type: 'health_problem', object_id: 8 },
    },
    {
      type: 'training',
      title: '[movement] 晚饭后步行 10 分钟',
      status: 'pending',
      priority: 70,
      time_window: 'evening',
      source: { object_type: 'daily_plan_action', object_id: 'walk' },
    },
    {
      type: 'hydration',
      title: '补水 200ml',
      status: 'completed',
      priority: 50,
      source: { object_type: 'health_protocol', object_id: 3 },
    },
  ],
};

jest.mock('expo-router', () => ({
  useRouter: () => ({
    back: mockBack,
    navigate: mockNavigate,
    push: jest.fn(),
    canGoBack: () => mockCanGoBack,
  }),
}));

jest.mock('../../hooks/useAgenda', () => ({
  useAgendaToday: () => ({
    data: mockAgendaData,
    isLoading: false,
    isError: false,
    isRefetching: false,
    refetch: jest.fn(),
  }),
  useCompleteAgendaItem: () => ({
    mutate: mockMutate,
    ...mockCompleteState,
  }),
  useSnoozeAgendaItem: () => ({ mutate: mockSnoozeMutate, ...mockSnoozeState }),
  useResumeAgendaItem: () => ({ mutate: mockResumeMutate, ...mockResumeState }),
  useSmartAgendaToday: () => ({ data: null, isLoading: false }),
  useRuntimeAgendaRange: () => ({ data: null, isLoading: false }),
  useSeedDemo: () => ({ mutate: jest.fn(), isPending: false }),
}));

jest.mock('../../hooks/useToast', () => ({
  useToast: () => ({ show: mockToast, showUndoable: mockShowUndoable }),
}));

jest.mock('../../utils/agentContext', () => ({
  pushChatWithContext: (...args: unknown[]) => mockPushChatWithContext(...args),
}));

jest.mock('expo-haptics', () => ({
  impactAsync: jest.fn().mockResolvedValue(undefined),
  notificationAsync: jest.fn().mockResolvedValue(undefined),
  ImpactFeedbackStyle: { Light: 'light', Medium: 'medium' },
  NotificationFeedbackType: { Success: 'success', Error: 'error' },
}));

import AgendaScreen from '../agenda';

describe('AgendaScreen', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-07-20T09:00:00-04:00'));
    jest.clearAllMocks();
    mockCanGoBack = true;
    mockAgendaData = agendaData;
    mockCompleteState = { isPending: false };
    mockSnoozeState = { isPending: false };
    mockResumeState = { isPending: false };
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  it('shows a compact today-only management hierarchy', () => {
    const { getByText, queryByText } = render(<AgendaScreen />);

    expect(getByText('今日行动')).toBeTruthy();
    expect(getByText('现在 1 · 待确认 1')).toBeTruthy();
    expect(queryByText('待处理 3 · 已处理 1')).toBeNull();
    expect(getByText('现在做')).toBeTruthy();
    expect(getByText('需要确认')).toBeTruthy();
    expect(getByText('稍后')).toBeTruthy();
    expect(getByText('已处理')).toBeTruthy();
    expect(getByText('晨间用药')).toBeTruthy();
    expect(queryByText('晚饭后步行 10 分钟')).toBeNull();
    expect(getByText('优质蛋白有助修复')).toBeTruthy();
    expect(queryByText('[movement] 晚饭后步行 10 分钟')).toBeNull();
    expect(queryByText('智能优先处理')).toBeNull();
    expect(queryByText('7 天健康运行时')).toBeNull();
  });

  it('keeps later actions collapsed until the user asks to inspect them', () => {
    const { getByLabelText, getByText, queryByText } = render(<AgendaScreen />);

    expect(queryByText('晚饭后步行 10 分钟')).toBeNull();
    expect(getByLabelText('展开稍后行动').props.accessibilityState).toEqual({ expanded: false });

    fireEvent.press(getByLabelText('展开稍后行动'));

    expect(getByText('晚饭后步行 10 分钟')).toBeTruthy();
    expect(getByLabelText('收起稍后行动').props.accessibilityState).toEqual({ expanded: true });
  });

  it('shows a clear-current-state note when only later or handled actions remain', () => {
    mockAgendaData = {
      agenda_date: '2026-07-20',
      count: 2,
      items: [
        agendaData.items[2],
        agendaData.items[3],
      ],
    };

    const { getByText, queryByText } = render(<AgendaScreen />);

    expect(getByText('现在 0 · 待确认 0')).toBeTruthy();
    expect(getByText('当前没有需要你立刻决策的行动')).toBeTruthy();
    expect(queryByText('晚饭后步行 10 分钟')).toBeNull();
  });

  it('returns through the stack and falls back to chat for a cold deep link', () => {
    const first = render(<AgendaScreen />);
    fireEvent.press(first.getByLabelText('返回小巴'));
    expect(mockBack).toHaveBeenCalledTimes(1);
    first.unmount();

    mockCanGoBack = false;
    const second = render(<AgendaScreen />);
    fireEvent.press(second.getByLabelText('返回小巴'));
    expect(mockNavigate).toHaveBeenCalledWith('/(tabs)/chat');
  });

  it('completes an actionable item through the verified agenda mutation', () => {
    const { getByLabelText } = render(<AgendaScreen />);
    fireEvent.press(getByLabelText('完成 晨间用药'));

    expect(mockMutate).toHaveBeenCalledWith(
      { source: { object_type: 'health_protocol', object_id: 2 } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it('locks the current writable row and hides unsupported completion controls', () => {
    mockCompleteState = {
      isPending: true,
      variables: { source: { object_type: 'health_protocol', object_id: 2 } },
    };
    const { getByLabelText, queryByLabelText } = render(<AgendaScreen />);

    expect(getByLabelText('完成 晨间用药')).toBeDisabled();
    expect(queryByLabelText('完成 晚饭后步行 10 分钟')).toBeNull();
  });

  it('locks every write control for the row while snooze is pending', () => {
    mockSnoozeState = {
      isPending: true,
      variables: { source: { object_type: 'health_protocol', object_id: 2 } },
    };
    const { getByLabelText } = render(<AgendaScreen />);

    expect(getByLabelText('完成 晨间用药')).toBeDisabled();
    expect(getByLabelText('管理 晨间用药')).toBeDisabled();
    expect(getByLabelText('完成 晨间用药').props.accessibilityState).toEqual({
      disabled: true,
      busy: true,
    });
  });

  it('locks every writable row while one health write is pending', () => {
    mockAgendaData = {
      agenda_date: '2026-07-20',
      count: 2,
      items: [
        agendaData.items[0],
        {
          ...agendaData.items[0],
          title: '午间补水',
          time_window: 'morning',
          source: { object_type: 'health_protocol', object_id: 9 },
        },
      ],
    };
    mockSnoozeState = {
      isPending: true,
      variables: { source: { object_type: 'health_protocol', object_id: 2 } },
    };

    const { getByLabelText } = render(<AgendaScreen />);

    expect(getByLabelText('完成 晨间用药')).toBeDisabled();
    expect(getByLabelText('完成 午间补水')).toBeDisabled();
    expect(getByLabelText('管理 午间补水')).toBeDisabled();
  });

  it('locks restore and menu controls with complete busy semantics', () => {
    mockAgendaData = {
      agenda_date: '2026-07-20',
      count: 1,
      items: [{
        ...agendaData.items[0],
        status: 'snoozed',
        snoozed_until: '2026-07-20T09:30:00-04:00',
      }],
    };
    mockResumeState = {
      isPending: true,
      variables: { source: { object_type: 'health_protocol', object_id: 2 } },
    };
    const { getByLabelText } = render(<AgendaScreen />);
    fireEvent.press(getByLabelText('展开稍后行动'));

    expect(getByLabelText('恢复 晨间用药').props.accessibilityState).toEqual({
      disabled: true,
      busy: true,
    });
    expect(getByLabelText('管理 晨间用药').props.accessibilityState).toEqual({
      disabled: true,
      busy: true,
    });
  });

  it('persists a 30 minute snooze without falsely recording completion', () => {
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((_options, callback) => callback(0));
    const { getByLabelText } = render(<AgendaScreen />);

    fireEvent.press(getByLabelText('管理 晨间用药'));

    expect(mockMutate).not.toHaveBeenCalled();
    expect(mockSnoozeMutate).toHaveBeenCalledWith(
      { source: { object_type: 'health_protocol', object_id: 2 } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it('restores a server-snoozed item through a verified write', () => {
    const snoozedUntil = '2026-07-20T09:30:00-04:00';
    mockAgendaData = {
      agenda_date: '2026-07-20',
      count: 1,
      items: [{
        ...agendaData.items[0],
        status: 'snoozed',
        snoozed_until: snoozedUntil,
      }],
    };
    const { getByLabelText, getByText } = render(<AgendaScreen />);
    fireEvent.press(getByLabelText('展开稍后行动'));

    const localDate = new Date(snoozedUntil);
    const localTime = `${String(localDate.getHours()).padStart(2, '0')}:${String(localDate.getMinutes()).padStart(2, '0')}`;
    expect(getByText(`${localTime} 再提醒`)).toBeTruthy();
    fireEvent.press(getByLabelText('恢复 晨间用药'));

    expect(mockResumeMutate).toHaveBeenCalledWith(
      { source: { object_type: 'health_protocol', object_id: 2 } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it('does not offer a fake session-only snooze for review items', () => {
    let menuOptions: readonly string[] = [];
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((options) => {
      menuOptions = options.options;
    });
    const { getByLabelText } = render(<AgendaScreen />);

    fireEvent.press(getByLabelText('管理 优质蛋白有助修复'));

    expect(menuOptions).toEqual(['调整计划', '取消']);
    expect(mockSnoozeMutate).not.toHaveBeenCalled();
  });

  it('does not offer another snooze while a server-snoozed item is later', () => {
    mockAgendaData = {
      agenda_date: '2026-07-20',
      count: 1,
      items: [{
        ...agendaData.items[0],
        status: 'snoozed',
        snoozed_until: '2026-07-20T09:30:00-04:00',
      }],
    };
    let menuOptions: readonly string[] = [];
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((options) => {
      menuOptions = options.options;
    });
    const { getByLabelText } = render(<AgendaScreen />);
    fireEvent.press(getByLabelText('展开稍后行动'));

    fireEvent.press(getByLabelText('管理 晨间用药'));

    expect(menuOptions).toEqual(['跳过', '调整计划', '问小巴', '取消']);
  });

  it('does not offer persistence it cannot honor for independent medication rows', () => {
    mockAgendaData = {
      agenda_date: '2026-07-20',
      count: 1,
      items: [{
        ...agendaData.items[0],
        source: { object_type: 'medication', object_id: 22 },
      }],
    };
    let menuOptions: readonly string[] = [];
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((options) => {
      menuOptions = options.options;
    });
    const { getByLabelText } = render(<AgendaScreen />);

    fireEvent.press(getByLabelText('管理 晨间用药'));

    expect(menuOptions).toEqual(['跳过', '调整计划', '问小巴', '取消']);
  });

  it('keeps future review items free of duplicate ask and defer actions', () => {
    let menuOptions: readonly string[] = [];
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((options) => {
      menuOptions = options.options;
    });
    const { getByLabelText } = render(<AgendaScreen />);
    fireEvent.press(getByLabelText('展开稍后行动'));

    fireEvent.press(getByLabelText('管理 晚饭后步行 10 分钟'));

    expect(menuOptions).toEqual(['调整计划', '取消']);
  });

  it('hides empty groups instead of filling the screen with empty headings', () => {
    mockAgendaData = {
      agenda_date: '2026-07-20',
      count: 1,
      items: [agendaData.items[0]],
    };
    const { getByText, queryByText } = render(<AgendaScreen />);

    expect(getByText('现在做')).toBeTruthy();
    expect(queryByText('需要确认')).toBeNull();
    expect(queryByText('稍后')).toBeNull();
    expect(queryByText('已处理')).toBeNull();
  });

  it('progressively reveals long review queues instead of expanding every item', () => {
    const reviewItems = Array.from({ length: 5 }, (_, index) => ({
      type: 'advisory',
      title: `待确认建议 ${index + 1}`,
      status: 'active',
      priority: 80 - index,
      time_window: 'anytime',
      source: { object_type: 'health_problem', object_id: 20 + index },
    }));
    mockAgendaData = {
      agenda_date: '2026-07-20',
      count: 6,
      items: [agendaData.items[0], ...reviewItems],
    };
    const { getByLabelText, getByText, queryByText } = render(<AgendaScreen />);

    expect(getByText('待确认建议 3')).toBeTruthy();
    expect(queryByText('待确认建议 4')).toBeNull();
    expect(getByLabelText('查看其余 2 项需要确认事项').props.accessibilityState).toEqual({ expanded: false });
    fireEvent.press(getByText('查看其余 2 项'));
    expect(getByText('待确认建议 4')).toBeTruthy();
    expect(getByText('待确认建议 5')).toBeTruthy();
    expect(getByText('收起')).toBeTruthy();
    expect(getByLabelText('收起需要确认事项').props.accessibilityState).toEqual({ expanded: true });
    fireEvent.press(getByText('收起'));
    expect(queryByText('待确认建议 4')).toBeNull();
  });

  it('does not offer unsupported skip writes for advisory items', () => {
    let menuOptions: readonly string[] = [];
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((options, callback) => {
      menuOptions = options.options;
      callback(0);
    });
    const { getByLabelText } = render(<AgendaScreen />);

    fireEvent.press(getByLabelText('管理 优质蛋白有助修复'));

    expect(menuOptions).toEqual(['调整计划', '取消']);
    expect(mockMutate).not.toHaveBeenCalled();
    expect(mockPushChatWithContext).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        context: expect.objectContaining({ intent: 'adjust' }),
      }),
    );
  });

  it('keeps the review-only menu safe on Android', () => {
    const originalOS = Platform.OS;
    let buttons: Parameters<typeof Alert.alert>[2];
    Object.defineProperty(Platform, 'OS', { value: 'android' });
    jest.spyOn(Alert, 'alert').mockImplementation((_title, _message, nextButtons) => {
      buttons = nextButtons;
    });

    try {
      const { getByLabelText } = render(<AgendaScreen />);
      fireEvent.press(getByLabelText('管理 优质蛋白有助修复'));

      expect(buttons?.map(button => button.text)).toEqual(['调整计划', '取消']);
      buttons?.[0]?.onPress?.();
      expect(mockMutate).not.toHaveBeenCalled();
      expect(mockPushChatWithContext).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ context: expect.objectContaining({ intent: 'adjust' }) }),
      );
    } finally {
      Object.defineProperty(Platform, 'OS', { value: originalOS });
    }
  });

  it('records an explicit skip reason instead of silently deleting the item', () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    let sheetCall = 0;
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((_options, callback) => {
      sheetCall += 1;
      callback(sheetCall === 1 ? 1 : 3);
    });
    const { getByLabelText } = render(<AgendaScreen />);

    fireEvent.press(getByLabelText('管理 晨间用药'));

    expect(ActionSheetIOS.showActionSheetWithOptions).toHaveBeenCalledTimes(2);
    expect(alertSpy).not.toHaveBeenCalled();
    expect(mockMutate).toHaveBeenCalledWith(
      {
        source: { object_type: 'health_protocol', object_id: 2 },
        status: 'skipped',
        skipReason: 'too_tired',
      },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });
});
