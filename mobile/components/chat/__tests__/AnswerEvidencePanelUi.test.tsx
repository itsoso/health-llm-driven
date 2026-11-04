import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import AnswerEvidencePanel from '../AnswerEvidencePanel';
import { buildAgentTransparency } from '../../../utils/chatTransparency';

const props = {
  profile: buildAgentTransparency({}), thinkingSteps: [],
  completionActionsEnabled: false, copied: false,
  onOpenMemory: jest.fn(), onShareWeChat: jest.fn(),
  onShareXiaohongshu: jest.fn(), onCopy: jest.fn(),
};

beforeEach(() => jest.clearAllMocks());

it('keeps platform choices hidden until sharing is explicitly opened', () => {
  const view = render(<AnswerEvidencePanel {...props} completionActionsEnabled sources={['今天打卡记录']} />);
  expect(view.queryByLabelText('微信分享这条回复')).toBeNull();
  expect(view.queryByLabelText('小红书分享这条回复')).toBeNull();
  expect(view.getByLabelText('分享回答')).toHaveStyle({ width: 44, height: 44 });
  fireEvent.press(view.getByLabelText('分享回答'));
  expect(props.onShareWeChat).not.toHaveBeenCalled();
  expect(props.onShareXiaohongshu).not.toHaveBeenCalled();
  expect(view.getByLabelText('展开回答依据')).toBeTruthy();
  expect(view.getByLabelText('微信分享这条回复')).toBeTruthy();
  expect(view.getByLabelText('小红书分享这条回复')).toBeTruthy();
  fireEvent.press(view.getByLabelText('收起分享选项'));
  expect(view.queryByLabelText('微信分享这条回复')).toBeNull();
});

it.each([
  ['微信分享这条回复', props.onShareWeChat, props.onShareXiaohongshu],
  ['小红书分享这条回复', props.onShareXiaohongshu, props.onShareWeChat],
] as const)('dispatches only the selected target and closes the options: %s', (label, selected, other) => {
  const view = render(<AnswerEvidencePanel {...props} completionActionsEnabled />);
  fireEvent.press(view.getByLabelText('分享回答'));
  fireEvent.press(view.getByLabelText(label));
  expect(selected).toHaveBeenCalledTimes(1);
  expect(other).not.toHaveBeenCalled();
  expect(view.queryByLabelText(label)).toBeNull();
});

it('dismisses open sharing when completion actions become unavailable', () => {
  const view = render(<AnswerEvidencePanel {...props} completionActionsEnabled />);
  fireEvent.press(view.getByLabelText('分享回答'));
  view.rerender(<AnswerEvidencePanel {...props} completionActionsEnabled={false} />);
  expect(view.queryByLabelText('微信分享这条回复')).toBeNull();
  view.rerender(<AnswerEvidencePanel {...props} completionActionsEnabled />);
  expect(view.queryByLabelText('微信分享这条回复')).toBeNull();
});

it('does not render an empty evidence rail', () => {
  const view = render(<AnswerEvidencePanel {...props} />);
  expect(view.queryByTestId('assistant-utility-panel')).toBeNull();
});

it('labels processing information separately and keeps technical details accessible', () => {
  const view = render(<AnswerEvidencePanel {...props}
    profile={buildAgentTransparency({ model: 'test-model', elapsedMs: 3000 })} />);
  expect(view.getByText('处理详情')).toBeTruthy();
  expect(view.queryByText('回答依据')).toBeNull();
  fireEvent.press(view.getByLabelText('展开处理详情'));
  expect(view.getByText('技术详情')).toBeTruthy();
});

it('keeps copy available when there is no evidence', () => {
  const view = render(<AnswerEvidencePanel {...props} completionActionsEnabled />);
  fireEvent.press(view.getByLabelText('复制回答'));
  expect(props.onCopy).toHaveBeenCalled();
});


it.each(['blocked', 'partial', 'failed'] as const)('does not show successful steps for a %s business outcome', terminalStatus => {
  const view = render(<AnswerEvidencePanel {...props} terminalStatus={terminalStatus}
    thinkingSteps={['已取得相关数据', '整理回复中', '查询失败']} />);
  fireEvent.press(view.getByLabelText('展开处理详情'));
  expect(view.getByText('本轮处理未完成')).toBeTruthy();
  expect(view.queryByLabelText('已完成：已取得相关数据')).toBeNull();
  expect(view.getByLabelText('处理阶段：已取得相关数据')).toBeTruthy();
  expect(view.getByLabelText('需要注意：查询失败')).toBeTruthy();
});

it('shows waiting for user as confirmation rather than a failed turn', () => {
  const view = render(<AnswerEvidencePanel {...props} terminalStatus="waiting_for_user"
    thinkingSteps={['识别图片', '理解你的问题']} />);
  fireEvent.press(view.getByLabelText('展开处理详情'));
  expect(view.getByText('等待你确认或补充信息')).toBeTruthy();
  expect(view.queryByText('本轮处理未完成')).toBeNull();
  expect(view.getByLabelText('处理阶段：识别图片')).toBeTruthy();
});

it('preserves actual interruption even with a stale waiting status', () => {
  const view = render(<AnswerEvidencePanel {...props} incomplete terminalStatus="waiting_for_user"
    thinkingSteps={['识别图片']} />);
  fireEvent.press(view.getByLabelText('展开处理详情'));
  expect(view.getByText('本轮处理未完成')).toBeTruthy();
});

it('does not claim completed steps for an interrupted generated response', () => {
  const view = render(<AnswerEvidencePanel {...props} incomplete terminalStatus="complete"
    thinkingSteps={['整理回复中']} />);
  fireEvent.press(view.getByLabelText('展开处理详情'));
  expect(view.getByText('本轮处理未完成')).toBeTruthy();
  expect(view.getByLabelText('处理阶段：整理回答')).toBeTruthy();
});


it('preserves completed process indicators for a successful business outcome', () => {
  const view = render(<AnswerEvidencePanel {...props} terminalStatus="complete"
    thinkingSteps={['检查健康数据', '整理回复中']} />);
  fireEvent.press(view.getByLabelText('展开处理详情'));
  expect(view.getByText('这条回答完成了 2 个处理步骤')).toBeTruthy();
  expect(view.getByLabelText('已完成：检查健康数据')).toBeTruthy();
  expect(view.queryByText('本轮处理未完成')).toBeNull();
});
