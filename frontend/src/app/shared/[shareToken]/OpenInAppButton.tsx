'use client';

import { useState } from 'react';

export function buildSharedDeepLinks(shareToken: string): string[] {
  const token = encodeURIComponent(shareToken);
  return [
    `health://shared/${token}`,
    `mobile://shared/${token}`,
    `https://health.executor.life/shared/${token}`,
  ];
}

export function openSharedInApp(
  shareToken: string,
  navigate: (url: string) => void = (url) => window.location.assign(url),
  isVisible: () => boolean = () => document.visibilityState !== 'hidden',
  setTimer: (callback: () => void, ms: number) => unknown = (callback, ms) => window.setTimeout(callback, ms),
) {
  const links = buildSharedDeepLinks(shareToken);
  navigate(links[0]);
  setTimer(() => {
    if (!isVisible()) return;
    navigate(links[1]);
    setTimer(() => {
      if (isVisible()) navigate(links[2]);
    }, 700);
  }, 700);
}

export default function OpenInAppButton({ shareToken }: { shareToken: string }) {
  const [attempted, setAttempted] = useState(false);
  const primaryLink = buildSharedDeepLinks(shareToken)[0];

  return (
    <a
      href={primaryLink}
      onClick={(event) => {
        event.preventDefault();
        setAttempted(true);
        openSharedInApp(shareToken);
      }}
      className="flex items-center justify-between rounded-2xl border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-800 shadow-sm hover:bg-teal-100"
    >
      <span className="font-medium">
        {attempted ? '正在打开 App...' : '在 App 里打开,体验完整健康助理'}
      </span>
      <span aria-hidden className="text-base">→</span>
    </a>
  );
}
