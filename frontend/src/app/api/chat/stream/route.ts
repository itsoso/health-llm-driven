import { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const body = await request.json();
  const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
  const token = request.headers.get('authorization');

  const response = await fetch(`${backendUrl}/api/v1/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: token } : {}),
    },
    body: JSON.stringify(body),
  });

  if (!response.ok || !response.body) {
    return new Response(
      JSON.stringify({ error: 'Backend stream failed' }),
      { status: response.status, headers: { 'Content-Type': 'application/json' } }
    );
  }

  return new Response(response.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}
