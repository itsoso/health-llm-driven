/* eslint-disable import/first */
import React from 'react';
import { ActionSheetIOS, Alert } from 'react-native';
import { fireEvent, render } from '@testing-library/react-native';

import type { AgendaToday } from '../../services/agenda';

const mockBack = jest.fn();
const mockNavigate = jest.fn();
const mockMutate = jest.fn();
const mockPushChatWithContext = jest.fn();
const mockToast = jest.fn();
const mockShowUndoable = jest.fn();
let mockCanGoBack = true;
let mockAgendaData: AgendaToday;
let mockCompleteState: {
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
    jest.clearAllMocks();
    mockCanGoBack = true;
    mockAgendaData = agendaData;
    mockCompleteState = { isPending: false };
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation(() => {});
  });

  afterEach(() => jest.restoreAllMocks());

  it('shows a compact today-only management hierarchy', () => {
    const { getByText, queryByText } = render(<AgendaScreen />);

    expect(getByText('今日行动')).toBeTruthy();
    expect(getByText('现在做')).toBeTruthy();
    expect(getByText('需要确认')).toBeTruthy();
    expect(getByText('稍后')).toBeTruthy();
    expect(getByText('已处理')).toBeTruthy();
    expect(getByText('晨间用药')).toBeTruthy();
    expect(getByText('晚饭后步行 10 分钟')).toBeTruthy();
    expect(getByText('优质蛋白有助修复')).toBeTruthy();
    expect(queryByText('[movement] 晚饭后步行 10 分钟')).toBeNull();
    expect(queryByText('智能优先处理')).toBeNull();
    expect(queryByText('7 天健康运行时')).toBeNull();
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

  it('can defer an item without falsely recording it as completed', () => {
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((_options, callback) => callback(0));
    const { getByLabelText, getAllByText } = render(<AgendaScreen />);

    fireEvent.press(getByLabelText('管理 晨间用药'));

    expect(mockMutate).not.toHaveBeenCalled();
    expect(mockShowUndoable).toHaveBeenCalledWith(
      '已放到稍后',
      expect.any(Function),
    );
    expect(getAllByText('稍后').length).toBeGreaterThan(0);
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
    const { getByText, queryByText } = render(<AgendaScreen />);

    expect(getByText('待确认建议 3')).toBeTruthy();
    expect(queryByText('待确认建议 4')).toBeNull();
    fireEvent.press(getByText('查看其余 2 项'));
    expect(getByText('待确认建议 4')).toBeTruthy();
    expect(getByText('待确认建议 5')).toBeTruthy();
    expect(getByText('收起')).toBeTruthy();
  });

  it('does not offer unsupported skip writes for advisory items', () => {
    let menuOptions: readonly string[] = [];
    jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((options, callback) => {
      menuOptions = options.options;
      callback(1);
    });
    const { getByLabelText } = render(<AgendaScreen />);

    fireEvent.press(getByLabelText('管理 优质蛋白有助修复'));

    expect(menuOptions).toEqual(['稍后再看', '调整计划', '问小巴', '取消']);
    expect(mockMutate).not.toHaveBeenCalled();
    expect(mockPushChatWithContext).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        context: expect.objectContaining({ intent: 'adjust' }),
      }),
    );
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
