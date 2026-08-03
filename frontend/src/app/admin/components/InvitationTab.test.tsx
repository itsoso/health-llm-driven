// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import InvitationTab from './InvitationTab';

vi.mock('./RegistrationInvitationPanel', () => ({ default: () => <section aria-label="手机号注册邀请">手机号注册邀请面板</section> }));

describe('InvitationTab registration boundaries', () => {
  it('places phone registration invitations before the clearly labeled legacy flow', () => {
    render(<InvitationTab invitationStats={null} invitationCodes={[]} applications={[]} invitationLoading={false} statusFilter="" setStatusFilter={vi.fn()} setShowCreateCode={vi.fn()} setSelectedApp={vi.fn()} handleDisableCode={vi.fn()} copyToClipboard={vi.fn()} formatDate={() => '-'} />);
    const registration = screen.getByLabelText('手机号注册邀请');
    const legacy = screen.getByRole('heading', { name: '旧版通用邀请码（不用于手机号注册）' });
    expect(registration.compareDocumentPosition(legacy) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
