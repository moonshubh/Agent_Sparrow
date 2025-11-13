import { NextResponse } from 'next/server'

export const runtime = 'edge'

export async function POST() {
  return NextResponse.json(
    {
      error:
        'The /api/chat endpoint is deprecated. Please use the AG-UI chat experience instead, which talks directly to the backend /api/v1/copilot/stream endpoint.',
    },
    { status: 410 },
  )
}

export async function GET() {
  return NextResponse.json(
    {
      error:
        'The /api/chat endpoint is deprecated. Please use the AG-UI chat experience instead, which talks directly to the backend /api/v1/copilot/stream endpoint.',
    },
    { status: 410 },
  )
}
