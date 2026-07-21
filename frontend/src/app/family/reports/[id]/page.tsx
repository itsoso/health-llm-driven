import ClientPage from './ClientPage';

export function generateStaticParams() {
  return [{ id: '_placeholder' }];
}

export default function Page() {
  return <ClientPage />;
}
