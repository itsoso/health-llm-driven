import { sanitizeChatErrorMessage } from '../chatErrorMessage';

describe('chatErrorMessage local quota policy', () => {
  it('explains monthly recovery without claiming provider exhaustion', () => {
    const message = sanitizeChatErrorMessage('user_monthly_token_limit');

    expect(message).toContain('下月 1 日恢复');
    expect(message).toContain('内容已保留');
    expect(message).not.toContain('模型额度已用尽');
  });

  it('explains daily recovery', () => {
    expect(sanitizeChatErrorMessage('user_daily_call_limit')).toContain('明日恢复');
  });
});
