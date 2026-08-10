// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/services/api/client';
import RegistrationInvitationPanel from './RegistrationInvitationPanel';

vi.mock('@/services/api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
const rows = [
  { id: 7, phone_masked: '+86 138****8000', note: '内测成员', status: 'send_failed', expires_at: '2999-08-09T12:00:00Z', created_at: '2026-08-02T12:00:00Z', updated_at: '2026-08-02T12:00:00Z', prepared_for_delivery: true },
  { id: 8, phone_masked: '+86 139****9000', note: null, status: 'consumed', expires_at: '2999-08-09T12:00:00Z', created_at: '2026-08-02T12:00:00Z', updated_at: '2026-08-02T12:00:00Z', prepared_for_delivery: false },
];
const prepared = { ...rows[0], status: 'sent', manual_code: 'A8M2K9QX', link_token: 'link-token-must-not-render', deep_link: 'health://invite?token=opaque-link-token', delivery_status: 'sent', delivery_error_code: null };
const mockList = () => vi.mocked(api.get).mockResolvedValue({ data: { items: rows, total: rows.length, limit: 20, offset: 0 } });

describe('RegistrationInvitationPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks(); mockList(); vi.stubGlobal('confirm', vi.fn(() => true));
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
    vi.spyOn(Storage.prototype, 'setItem');
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('lists only safe fields with Chinese statuses and terminal controls', async () => {
    render(<RegistrationInvitationPanel />);
    expect(await screen.findByText('+86 138****8000')).toBeInTheDocument();
    expect(screen.getByText('发送失败')).toBeInTheDocument(); expect(screen.getByText('已使用')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重发 +86 138****8000 的邀请' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '撤销 +86 138****8000 的邀请' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '撤销 +86 139****9000 的邀请' })).toBeDisabled();
    expect(screen.queryByText(/13800138000/)).not.toBeInTheDocument(); expect(screen.queryByText(/digest|ciphertext/i)).not.toBeInTheDocument();
  });

  it('derives expired state from expires_at and disables active-status actions', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { items: [{ ...rows[0], status: 'sent', expires_at: '2000-01-01T00:00:00Z' }], total: 1, limit: 20, offset: 0 } });
    render(<RegistrationInvitationPanel />);
    expect(await screen.findByText('已过期')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重发 +86 138****8000 的邀请' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '撤销 +86 138****8000 的邀请' })).toBeDisabled();
  });

  it('fails closed for unknown statuses and invalid or missing expiry values', async () => {
    const unsafeRows = [
      { ...rows[0], id: 21, phone_masked: '+86 131****1000', status: 'provider_pending' },
      { ...rows[0], id: 22, phone_masked: '+86 132****2000', status: 'sent', expires_at: 'not-a-date' },
      { ...rows[0], id: 23, phone_masked: '+86 133****3000', status: 'sent', expires_at: undefined },
    ];
    vi.mocked(api.get).mockResolvedValue({ data: { items: unsafeRows, total: 3, limit: 20, offset: 0 } });
    render(<RegistrationInvitationPanel />);
    expect(await screen.findAllByText('状态异常')).toHaveLength(3);
    for (const phone of ['+86 131****1000', '+86 132****2000', '+86 133****3000']) {
      expect(screen.getByRole('button', { name: `重发 ${phone} 的邀请` })).toBeDisabled();
      expect(screen.getByRole('button', { name: `撤销 ${phone} 的邀请` })).toBeDisabled();
    }
  });

  it('initializes expiry to local now plus seven days and describes local time in confirmation', async () => {
    const before = Date.now(); render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    const expiry = screen.getByLabelText('有效期') as HTMLInputElement;
    const parsed = new Date(expiry.value).getTime();
    expect(parsed - before).toBeGreaterThan(7 * 24 * 60 * 60 * 1000 - 60_000);
    expect(parsed - before).toBeLessThan(7 * 24 * 60 * 60 * 1000 + 60_000);
    fireEvent.change(screen.getByLabelText('受邀手机号'), { target: { value: '+8613800138000' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    const dialog = screen.getByRole('dialog', { name: '确认创建手机号注册邀请' });
    expect(within(dialog).getByText(/有效期：\d{4}/)).toBeInTheDocument();
    expect(within(dialog).getByText(/本地时区：/)).toBeInTheDocument();
  });

  it('confirms a locally masked phone before creating with the generated contract', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: prepared }); render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    fireEvent.change(screen.getByLabelText('受邀手机号'), { target: { value: '+8613800138000' } });
    fireEvent.change(screen.getByLabelText('备注'), { target: { value: '产品内测' } });
    fireEvent.change(screen.getByLabelText('有效期'), { target: { value: '2999-08-09T20:00' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    const confirmation = screen.getByRole('dialog', { name: '确认创建手机号注册邀请' });
    expect(within(confirmation).getByText('+86 138****8000')).toBeInTheDocument(); expect(within(confirmation).queryByText('+8613800138000')).not.toBeInTheDocument();
    fireEvent.click(within(confirmation).getByRole('button', { name: '确认创建并发送' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/admin/registration-invitations', { phone: '+8613800138000', note: '产品内测', expires_at: new Date('2999-08-09T20:00').toISOString() }));
    expect(await screen.findByRole('dialog', { name: '一次性注册凭据' })).toBeInTheDocument(); expect(Storage.prototype.setItem).not.toHaveBeenCalled();
  });

  it('shows prepared credentials once, copies them, and clears them when closed', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: prepared }); render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    fireEvent.click(screen.getByRole('button', { name: '重发 +86 138****8000 的邀请' }));
    const dialog = await screen.findByRole('dialog', { name: '一次性注册凭据' });
    expect(api.post).toHaveBeenCalledWith('/admin/registration-invitations/7/resend');
    expect(within(dialog).getByDisplayValue('A8M2K9QX')).toBeInTheDocument(); expect(within(dialog).getByDisplayValue('health://invite?token=opaque-link-token')).toBeInTheDocument();
    expect(screen.queryByText('link-token-must-not-render')).not.toBeInTheDocument(); expect(within(dialog).getByText(/旧凭据已失效/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '复制手动邀请码' })); await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith('A8M2K9QX'));
    fireEvent.click(within(dialog).getByRole('button', { name: '关闭一次性凭据' })); expect(screen.queryByDisplayValue('A8M2K9QX')).not.toBeInTheDocument(); expect(Storage.prototype.setItem).not.toHaveBeenCalled();
  });

  it('keeps credentials selectable when clipboard access fails', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: prepared }); vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error('blocked'));
    render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000'); fireEvent.click(screen.getByRole('button', { name: '重发 +86 138****8000 的邀请' }));
    const dialog = await screen.findByRole('dialog', { name: '一次性注册凭据' }); fireEvent.click(within(dialog).getByRole('button', { name: '复制手动邀请码' }));
    expect(await within(dialog).findByText('复制失败，请手动选择上方内容。')).toBeInTheDocument(); expect(within(dialog).getByLabelText('手动邀请码')).toHaveAttribute('readonly');
  });

  it('maps delivery failures without exposing provider details', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { ...prepared, delivery_status: 'send_failed', delivery_error_code: 'sms_not_configured' } });
    render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    fireEvent.click(screen.getByRole('button', { name: '重发 +86 138****8000 的邀请' }));
    const dialog = await screen.findByRole('dialog', { name: '一次性注册凭据' });
    expect(within(dialog).getByText(/短信服务未配置/)).toBeInTheDocument();
    expect(within(dialog).queryByText('sms_not_configured')).not.toBeInTheDocument();
  });

  it('confirms revoke and never renders server details', async () => {
    vi.mocked(api.post).mockRejectedValueOnce({ response: { status: 500, data: { detail: 'SQL SELECT phone_ciphertext' } } }); render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    fireEvent.click(screen.getByRole('button', { name: '撤销 +86 138****8000 的邀请' }));
    expect(confirm).toHaveBeenCalledWith('确认撤销发给 +86 138****8000 的注册邀请？撤销后凭据立即失效。');
    expect(api.post).toHaveBeenCalledWith('/admin/registration-invitations/7/revoke');
    expect(await screen.findByText('服务暂时不可用，请稍后重试。')).toBeInTheDocument(); expect(screen.queryByText(/SQL SELECT|phone_ciphertext/)).not.toBeInTheDocument();
  });

  it('shows loading, empty, retryable error and refresh states accessibly', async () => {
    let resolveList: ((value: unknown) => void) | undefined;
    vi.mocked(api.get).mockImplementationOnce(() => new Promise((resolve) => { resolveList = resolve; }) as never);
    const { unmount } = render(<RegistrationInvitationPanel />); expect(screen.getByRole('status')).toHaveTextContent('正在加载手机号注册邀请');
    resolveList?.({ data: { items: [], total: 0, limit: 20, offset: 0 } }); expect(await screen.findByText('还没有手机号注册邀请')).toBeInTheDocument(); unmount();
    vi.mocked(api.get).mockRejectedValueOnce({ response: { status: 403 } }); render(<RegistrationInvitationPanel />);
    expect(await screen.findByRole('alert')).toHaveTextContent('没有权限执行此操作。'); expect(screen.getByRole('button', { name: '重新加载' })).toBeInTheDocument(); expect(screen.getByRole('button', { name: '刷新列表' })).toBeInTheDocument();
    expect(screen.queryByText('还没有手机号注册邀请')).not.toBeInTheDocument();
    expect(screen.queryByText(/共 \d+ 条/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '上一页' })).not.toBeInTheDocument();
  });

  it('clears stale list and pagination when a refresh fails', async () => {
    render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    vi.mocked(api.get).mockRejectedValueOnce({ response: { status: 500 } });
    fireEvent.click(screen.getByRole('button', { name: '刷新列表' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('服务暂时不可用');
    expect(screen.queryByText('+86 138****8000')).not.toBeInTheDocument();
    expect(screen.queryByText(/共 \d+ 条/)).not.toBeInTheDocument();
  });

  it('serializes mutations globally and locks the background while secrets are open', async () => {
    const activeRows = [rows[0], { ...rows[0], id: 9, phone_masked: '+86 137****7000', status: 'sent' }];
    vi.mocked(api.get).mockResolvedValue({ data: { items: activeRows, total: 2, limit: 20, offset: 0 } });
    let resolvePost: ((value: unknown) => void) | undefined;
    vi.mocked(api.post).mockImplementationOnce(() => new Promise((resolve) => { resolvePost = resolve; }) as never);
    render(<RegistrationInvitationPanel />); await screen.findByText('+86 137****7000');

    fireEvent.click(screen.getByRole('button', { name: '重发 +86 138****8000 的邀请' }));
    const secondResend = screen.getByRole('button', { name: '重发 +86 137****7000 的邀请' });
    expect(secondResend).toBeDisabled();
    fireEvent.click(secondResend);
    expect(api.post).toHaveBeenCalledTimes(1);

    resolvePost?.({ data: prepared });
    const dialog = await screen.findByRole('dialog', { name: '一次性注册凭据' });
    expect(screen.getByLabelText('受邀手机号')).toBeDisabled();
    expect(screen.getByRole('button', { name: '重发 +86 137****7000 的邀请', hidden: true })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '重发 +86 137****7000 的邀请', hidden: true }));
    expect(api.post).toHaveBeenCalledTimes(1);
    fireEvent.click(within(dialog).getByRole('button', { name: '关闭一次性凭据' }));
    expect(screen.getByRole('button', { name: '重发 +86 137****7000 的邀请' })).toBeEnabled();
  });

  it('traps confirmation focus, closes on Escape, and restores its trigger without submitting', async () => {
    render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    fireEvent.change(screen.getByLabelText('受邀手机号'), { target: { value: '+8613800138000' } });
    fireEvent.change(screen.getByLabelText('有效期'), { target: { value: '2999-08-09T20:00' } });
    const trigger = screen.getByRole('button', { name: '预览并确认' }); trigger.focus(); fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '确认创建手机号注册邀请' });
    expect(dialog).toHaveAttribute('aria-describedby', 'confirm-invitation-description');
    const first = within(dialog).getByRole('button', { name: '返回修改' });
    const last = within(dialog).getByRole('button', { name: '确认创建并发送' });
    await waitFor(() => expect(first).toHaveFocus());
    last.focus(); fireEvent.keyDown(dialog, { key: 'Tab' }); expect(first).toHaveFocus();
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true }); expect(last).toHaveFocus();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: '确认创建手机号注册邀请' })).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled(); await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('portals the modal outside the panel and makes app roots inert until close', async () => {
    render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    const appRoot = screen.getByLabelText('受邀手机号').closest('body > div') as HTMLElement;
    appRoot.setAttribute('aria-hidden', 'false');
    const sequence: string[] = [];
    const originalFocus = HTMLElement.prototype.focus;
    const originalSetAttribute = HTMLElement.prototype.setAttribute;
    vi.spyOn(HTMLElement.prototype, 'focus').mockImplementation(function (options) {
      if (this.hasAttribute('data-autofocus')) sequence.push('initial-focus');
      originalFocus.call(this, options);
    });
    vi.spyOn(HTMLElement.prototype, 'setAttribute').mockImplementation(function (name, value) {
      if (this === appRoot && name === 'inert') sequence.push('background-inert');
      originalSetAttribute.call(this, name, value);
    });
    fireEvent.change(screen.getByLabelText('受邀手机号'), { target: { value: '+8613800138000' } });
    const trigger = screen.getByRole('button', { name: '预览并确认' });
    trigger.focus(); fireEvent.click(trigger);
    const dialog = await screen.findByRole('dialog', { name: '确认创建手机号注册邀请' });
    expect(dialog.closest('section')).toBeNull();
    expect(sequence).toEqual(['initial-focus', 'background-inert']);
    expect(appRoot).toHaveAttribute('inert');
    expect(appRoot).toHaveAttribute('aria-hidden', 'true');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(appRoot).not.toHaveAttribute('inert'));
    expect(appRoot).toHaveAttribute('aria-hidden', 'false');
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('rejects invalid and past expiry values before preview', async () => {
    render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    fireEvent.change(screen.getByLabelText('受邀手机号'), { target: { value: '+8613800138000' } });
    const expiry = screen.getByLabelText('有效期');
    const preview = screen.getByRole('button', { name: '预览并确认' });
    fireEvent.change(expiry, { target: { value: '' } });
    expect(preview).toBeDisabled();
    fireEvent.change(expiry, { target: { value: '2000-01-01T00:00' } });
    expect(preview).toBeDisabled();
  });

  it('fails safely when expiry becomes invalid after preview and releases the mutation lock', async () => {
    render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    const phoneInput = screen.getByLabelText('受邀手机号');
    const expiry = screen.getByLabelText('有效期');
    fireEvent.change(phoneInput, { target: { value: '+8613800138000' } });
    fireEvent.change(expiry, { target: { value: '2999-08-09T20:00' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    const dialog = screen.getByRole('dialog', { name: '确认创建手机号注册邀请' });
    fireEvent.change(expiry, { target: { value: '' } });
    expect(within(dialog).getByText(/有效期：时间格式无效/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '确认创建并发送' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('有效期必须晚于当前时间，请修改后重试。');
    expect(api.post).not.toHaveBeenCalled();
    expect(phoneInput).toBeEnabled();
  });

  it('fails safely when expiry becomes past after preview and releases the mutation lock', async () => {
    render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    const phoneInput = screen.getByLabelText('受邀手机号');
    const expiry = screen.getByLabelText('有效期');
    fireEvent.change(phoneInput, { target: { value: '+8613800138000' } });
    fireEvent.change(expiry, { target: { value: '2999-08-09T20:00' } });
    fireEvent.click(screen.getByRole('button', { name: '预览并确认' }));
    const dialog = screen.getByRole('dialog', { name: '确认创建手机号注册邀请' });
    fireEvent.change(expiry, { target: { value: '2000-01-01T00:00' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '确认创建并发送' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('有效期必须晚于当前时间，请修改后重试。');
    expect(api.post).not.toHaveBeenCalled();
    expect(phoneInput).toBeEnabled();
  });

  it('traps prepared focus, clears secrets on Escape, and restores the row trigger', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: prepared }); render(<RegistrationInvitationPanel />); await screen.findByText('+86 138****8000');
    const trigger = screen.getByRole('button', { name: '重发 +86 138****8000 的邀请' }); trigger.focus(); fireEvent.click(trigger);
    const dialog = await screen.findByRole('dialog', { name: '一次性注册凭据' });
    expect(dialog).toHaveAttribute('aria-describedby', 'prepared-invitation-description');
    const first = within(dialog).getByLabelText('手动邀请码');
    const last = within(dialog).getByRole('button', { name: '关闭一次性凭据' });
    await waitFor(() => expect(first).toHaveFocus());
    last.focus(); fireEvent.keyDown(dialog, { key: 'Tab' }); expect(first).toHaveFocus();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByDisplayValue('A8M2K9QX')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: '重发 +86 138****8000 的邀请' })).toHaveFocus());
  });

  it('keeps only the latest list response when older requests finish late', async () => {
    let resolveOld: ((value: unknown) => void) | undefined;
    let resolveNew: ((value: unknown) => void) | undefined;
    vi.mocked(api.get)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }) as never)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveNew = resolve; }) as never);
    render(<RegistrationInvitationPanel />);
    fireEvent.click(screen.getByRole('button', { name: '刷新列表' }));
    const latest = { ...rows[0], id: 70, phone_masked: '+86 170****7000' };
    resolveNew?.({ data: { items: [latest], total: 1, limit: 20, offset: 0 } });
    expect(await screen.findByText('+86 170****7000')).toBeInTheDocument();
    resolveOld?.({ data: { items: rows, total: 2, limit: 20, offset: 0 } });
    await waitFor(() => expect(screen.queryByText('+86 138****8000')).not.toBeInTheDocument());
  });

  it('aborts on unmount and ignores late responses without surfacing an error', async () => {
    let resolveList: ((value: unknown) => void) | undefined;
    vi.mocked(api.get).mockImplementationOnce((_url, config) => {
      expect(config?.signal).toBeInstanceOf(AbortSignal);
      return new Promise((resolve) => { resolveList = resolve; }) as never;
    });
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { unmount } = render(<RegistrationInvitationPanel />);
    const signal = vi.mocked(api.get).mock.calls[0][1]?.signal;
    unmount();
    expect(signal?.aborted).toBe(true);
    resolveList?.({ data: { items: rows, total: 2, limit: 20, offset: 0 } });
    await Promise.resolve();
    expect(consoleError).not.toHaveBeenCalled();
  });

  it('does not show an error when a superseded request rejects with AbortError', async () => {
    let rejectOld: ((reason?: unknown) => void) | undefined;
    vi.mocked(api.get)
      .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject; }) as never)
      .mockResolvedValueOnce({ data: { items: [], total: 0, limit: 20, offset: 0 } });
    render(<RegistrationInvitationPanel />);
    fireEvent.click(screen.getByRole('button', { name: '刷新列表' }));
    expect(await screen.findByText('还没有手机号注册邀请')).toBeInTheDocument();
    rejectOld?.(new DOMException('aborted', 'AbortError'));
    await Promise.resolve();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
