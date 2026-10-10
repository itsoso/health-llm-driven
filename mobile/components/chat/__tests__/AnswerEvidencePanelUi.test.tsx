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
