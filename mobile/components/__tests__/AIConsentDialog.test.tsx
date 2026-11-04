import React from 'react';
import { act, fireEvent, render } from '@testing-library/react-native';
import { AIConsentDialog } from '../AIConsentDialog';
import { showAIConsent, getConsentPresentation } from '../../services/aiConsentPresentation';
import { setAIConsentIdentity } from '../../services/aiConsentState';

const policy = { policy_version: 'v1', accepted: false, accepted_at: null,
  recipients: [{ id: 'provider', name: '实际模型服务商', purpose: '语音转写与对话' }],
  data_types: ['选定的语音', '相关健康记录'], purpose: '完成本次请求' };

beforeEach(() => { setAIConsentIdentity('test'); });
afterEach(() => { act(() => { getConsentPresentation()?.choose('decline'); }); });
it('shows the actual recipient, data and purpose with separate explicit choices', async () => {
  const view = render(<AIConsentDialog />);
  let decision!: Promise<string>;
  act(() => { decision = showAIConsent(policy, 'request'); });
  expect(view.getByText('实际模型服务商')).toBeTruthy();
  expect(view.getByText('• 相关健康记录')).toBeTruthy();
  expect(view.getByText('完成本次请求')).toBeTruthy();
  fireEvent.press(view.getByText('暂不使用'));
  await expect(decision).resolves.toBe('decline');
  expect(view.queryByText('同意并继续')).toBeNull();
});
it('only returns acceptance after the explicit button press', async () => {
  const view = render(<AIConsentDialog />);
  let decision!: Promise<string>;
  act(() => { decision = showAIConsent(policy, 'request'); });
  fireEvent.press(view.getByText('同意并继续'));
  await expect(decision).resolves.toBe('accept');
});
it('closes and denies a pending decision when the account changes', async () => {
  const view = render(<AIConsentDialog />);
  let decision!: Promise<string>;
  act(() => { decision = showAIConsent(policy, 'request'); });
  act(() => { setAIConsentIdentity('other-account'); });
  await expect(decision).resolves.toBe('decline');
  expect(view.queryByText('同意并继续')).toBeNull();
});
it('makes withdrawal available without reinterpreting it as acceptance', async () => {
  const view = render(<AIConsentDialog />);
  let decision!: Promise<string>;
  act(() => { decision = showAIConsent({ ...policy, accepted: true }, 'manage'); });
  expect(view.queryByText('同意并继续')).toBeNull();
  fireEvent.press(view.getByText('撤回授权'));
  await expect(decision).resolves.toBe('revoke');
});

it('denies the current replacement request when its screen is closed', async () => {
  const Screen = require('../../app/ai-consent').default;
  let first!: Promise<string>;
  act(() => { first = showAIConsent(policy, 'request'); });
  const view = render(<Screen />);
  let second!: Promise<string>;
  act(() => { second = showAIConsent(policy, 'manage'); });
  await expect(first).resolves.toBe('decline');
  view.unmount();
  await expect(second).resolves.toBe('decline');
  expect(getConsentPresentation()).toBeNull();
});
