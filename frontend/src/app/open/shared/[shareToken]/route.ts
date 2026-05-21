import { NextRequest, NextResponse } from 'next/server';

export function GET(_request: NextRequest, { params }: { params: { shareToken: string } }) {
  const token = encodeURIComponent(params.shareToken);
  return NextResponse.redirect(new URL(`/shared/${token}`, 'https://health.executor.life'), 307);
}
