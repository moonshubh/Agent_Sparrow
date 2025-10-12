/**
 * Supabase Storage helpers for FeedMe assets (images pasted into the canvas)
 */

import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL as string | undefined
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string | undefined
const LOCAL_BYPASS = process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true'
const BUCKET = process.env.NEXT_PUBLIC_FEEDME_ASSETS_BUCKET || 'feedme-assets'

// Provide a safe client in all modes:
// - Real Supabase client when env is configured
// - Minimal mock in local bypass mode to avoid runtime errors
// - Throw explicit error otherwise
const supabase = (() => {
  if (SUPABASE_URL && SUPABASE_ANON_KEY) {
    return createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  }
  if (LOCAL_BYPASS) {
    console.warn('Supabase storage disabled (local bypass). Uploads will be no-ops.')
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mock: any = {
      storage: {
        from: (_bucket: string) => ({
          upload: async (_path: string, _file: File, _opts?: any) => ({ data: { path: _path }, error: null }),
          getPublicUrl: (_path: string) => ({ data: { publicUrl: '' }, error: null }),
        }),
      },
    }
    return mock
  }
  throw new Error('Supabase storage is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY')
})()

function extFromMime(mime: string): string {
  if (!mime) return 'bin'
  const map: Record<string, string> = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/webp': 'webp',
    'image/gif': 'gif',
    'image/svg+xml': 'svg',
  }
  return map[mime] || 'bin'
}

export async function uploadImageToSupabase(
  file: File,
  conversationId?: number
): Promise<string> {
  const client = supabase

  const ext = extFromMime(file.type)
  const ts = Date.now()
  const uid = Math.random().toString(36).slice(2)
  const path = `conversations/${conversationId || 'general'}/${ts}-${uid}.${ext}`

  const { error } = await client.storage.from(BUCKET).upload(path, file, {
    contentType: file.type || 'application/octet-stream',
    upsert: false,
  })
  if (error) throw error

  // Prefer public URL for simplicity; configure the bucket as public or switch to signed URLs as needed
  const { data } = client.storage.from(BUCKET).getPublicUrl(path)
  if (!data?.publicUrl) throw new Error('Failed to obtain public URL for uploaded image')
  return data.publicUrl
}
