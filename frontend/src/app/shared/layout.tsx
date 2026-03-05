import React from 'react';

export default function SharedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 overflow-auto bg-slate-950">
      <style>{`
        nav, footer, .quick-action-button { display: none !important; }
        main { margin-top: 0 !important; }
      `}</style>
      {children}
    </div>
  );
}
