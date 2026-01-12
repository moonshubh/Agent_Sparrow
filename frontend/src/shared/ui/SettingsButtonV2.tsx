"use client"

import { useMemo, useState } from 'react'
import { Settings } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/shared/ui/tooltip'
import { SettingsDialogV2 } from '@/features/settings/components/SettingsDialogV2'
import { useRouter, useSearchParams } from 'next/navigation'

export function SettingsButtonV2() {
  const [manualOpen, setManualOpen] = useState(false)
  const searchParams = useSearchParams()
  const router = useRouter()

  const settingsParam = useMemo(() => (searchParams?.get('settings') || '').toLowerCase(), [searchParams])

  const allowedTabs = useMemo(() => (
    new Set(['general', 'api-keys', 'zendesk', 'rate-limits', 'account'])
  ), [])
  const paramTab = allowedTabs.has(settingsParam) ? settingsParam : null
  const defaultTab = (paramTab ?? 'general') as 'general' | 'api-keys' | 'zendesk' | 'rate-limits' | 'account'
  const isOpen = manualOpen || Boolean(paramTab)

  const handleClose = () => {
    setManualOpen(false)
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
              onClick={() => setManualOpen(true)}
              aria-label="Open settings"
            >
              <Settings className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Settings</TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <SettingsDialogV2
        key={defaultTab}
        isOpen={isOpen}
        onClose={handleClose}
        defaultTab={defaultTab}
      />
    </>
  )
}
