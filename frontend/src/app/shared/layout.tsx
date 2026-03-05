import React from 'react';

export default function SharedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div className="fixed inset-0 z-50 overflow-auto">{children}</div>;
}
