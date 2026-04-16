import dynamic from 'next/dynamic';

const ClientPage = dynamic(() => import('./ClientPage'), { ssr: false });

export function generateStaticParams() {
  return [{ token: '_placeholder' }];
}

export default function Page() {
  return <ClientPage />;
}
