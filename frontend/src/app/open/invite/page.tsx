import type { Metadata } from 'next';
import RegistrationInviteLanding from './RegistrationInviteLanding';

export const metadata: Metadata = {
  title: '打开小巴健康注册邀请',
  robots: { index: false, follow: false },
  referrer: 'no-referrer',
};

export default function RegistrationInvitePage() {
  return <RegistrationInviteLanding />;
}
