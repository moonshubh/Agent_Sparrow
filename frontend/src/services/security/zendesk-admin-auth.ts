import { cookies } from 'next/headers'
import { createServerClient } from '@supabase/ssr'
import type { User } from '@supabase/supabase-js'

type AuthResult = {
  ok: boolean
  user: User | null
  reason?: 'not_authenticated' | 'forbidden' | 'unsupported'
}

const isLocalBypass = () => process.env.NEXT_PUBLIC_LOCAL_AUTH_BYPASS === 'true'

const parseList = (value: string | undefined) =>
  (value || '')
    .split(',')
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean)

export async function verifyZendeskAdminAccess(): Promise<AuthResult> {
  if (isLocalBypass()) {
    return { ok: true, user: null }
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  if (!supabaseUrl || !supabaseAnonKey) {
    return { ok: false, user: null, reason: 'unsupported' }
  }

  const cookieStore = await cookies()
  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      get(name: string) {
        return cookieStore.get(name)?.value
      },
      set() {
        /* no-op */
      },
      remove() {
        /* no-op */
      },
    },
  })

  const { data, error } = await supabase.auth.getUser()
  const user = data?.user || null

  if (error || !user) {
    return { ok: false, user: null, reason: 'not_authenticated' }
  }

  const allowedEmails = parseList(process.env.ZENDESK_ADMIN_EMAILS)
  const allowedRoles = parseList(process.env.ZENDESK_ADMIN_ROLES || 'admin')

  const email = user.email?.toLowerCase()
  const role = (
    user.user_metadata?.role ||
    user.app_metadata?.role ||
    user.role
  )
    ?.toString()
    .toLowerCase()

  const emailAllowed = allowedEmails.length === 0 || (email && allowedEmails.includes(email))
  const roleAllowed = allowedRoles.length === 0 || (role && allowedRoles.includes(role))

  if (!emailAllowed || !roleAllowed) {
    return { ok: false, user, reason: 'forbidden' }
  }

  return { ok: true, user }
}

export async function buildAuthCookieHeader(): Promise<string> {
  const cookieStore = await cookies()
  return cookieStore
    .getAll()
    .map(({ name, value }) => `${name}=${value}`)
    .join('; ')
}
