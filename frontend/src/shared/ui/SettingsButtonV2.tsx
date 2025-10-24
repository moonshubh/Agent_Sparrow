"use client"

import { useEffect, useMemo, useState } from 'react'
import { Settings } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip'
import { SettingsDialogV2 } from '@/features/settings/components/SettingsDialogV2'
import { useRouter, useSearchParams } from 'next/navigation'

export function SettingsButtonV2() {
  const [open, setOpen] = useState(false)
  const [defaultTab, setDefaultTab] = useState<string>('general')
  const searchParams = useSearchParams()
  const router = useRouter()

  const settingsParam = useMemo(() => (searchParams?.get('settings') || '').toLowerCase(), [searchParams])

  useEffect(() => {
    const allowed = new Set(['general', 'api-keys', 'zendesk', 'global-knowledge', 'rate-limits', 'account'])
    if (allowed.has(settingsParam)) {
      setDefaultTab(settingsParam)
      setOpen(true)
    }
  }, [settingsParam])

  const handleClose = () => {
    setOpen(false)
    try {
      const sp = new URLSearchParams(Array.from(searchParams?.entries?.() || []))
      sp.delete('settings')
      const q = sp.toString()
      const url = `${typeof window !== 'undefined' ? window.location.pathname : '/'}${q ? `?${q}` : ''}`
      router.replace(url)
    } catch {
      /* no-op */
    }
  }

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => setOpen(true)}
              aria-label="Open settings"
            >
              <Settings className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Settings</TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <SettingsDialogV2 isOpen={open} onClose={handleClose} defaultTab={defaultTab as any} />
    </>
  )
}
