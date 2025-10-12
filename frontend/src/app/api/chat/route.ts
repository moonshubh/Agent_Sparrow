import { NextResponse } from 'next/server'

export const runtime = 'edge'

export async function POST() {
  return NextResponse.json(
    {
      error: 'The /api/chat endpoint is deprecated. Please call the backend /api/v1/v2/agent/chat/stream endpoint directly via the unified client.',
    },
    { status: 410 },
  )
}

export async function GET() {
  return NextResponse.json(
    {
      error: 'The /api/chat endpoint is deprecated. Please call the backend /api/v1/v2/agent/chat/stream endpoint directly via the unified client.',
    },
    { status: 410 },
  )
}
