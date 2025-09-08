"use client"

import React, { useState } from "react"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"
import { Settings } from "lucide-react"
import { SettingsDialogV2 } from "@/components/settings/SettingsDialogV2"

export function SettingsButtonV2() {
  const [open, setOpen] = useState(false)

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
      <SettingsDialogV2 isOpen={open} onClose={() => setOpen(false)} />
    </>
  )
}

