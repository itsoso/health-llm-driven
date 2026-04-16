import dynamic from 'next/dynamic';

const ClientPage = dynamic(() => import('./ClientPage'), { ssr: false });

export function generateStaticParams() {
  return [{ id: '_placeholder' }];
}

export default function Page() {
  return <ClientPage />;
}
