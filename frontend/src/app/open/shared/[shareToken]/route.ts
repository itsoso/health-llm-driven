import { NextRequest, NextResponse } from 'next/server';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ shareToken: string }> },
) {
  const { shareToken } = await params;
  const token = encodeURIComponent(shareToken);
  return NextResponse.redirect(new URL(`/shared/${token}`, 'https://health.executor.life'), 307);
}
