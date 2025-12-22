"use client"

import React, { useCallback } from "react"
import { useTheme } from "next-themes"
import { Separator } from "@/shared/ui/separator"
import { Switch } from "@/shared/ui/switch"
import { Label } from "@/shared/ui/label"

export function GeneralPanel() {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const selected = theme === "system" ? resolvedTheme : theme

  const isDark = selected === "dark"
  const onToggleDark = useCallback((next: boolean) => {
    setTheme(next ? "dark" : "light")
  }, [setTheme])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">General</h2>
        <p className="text-sm text-muted-foreground">Basic preferences for appearance.</p>
      </div>

      <Separator />

      <div className="rounded-md border p-4 space-y-4">
        <h3 className="text-sm font-medium">Appearance</h3>
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm font-medium">Dark Mode</div>
            <div className="text-xs text-muted-foreground">Toggle application theme</div>
          </div>
          <Switch
            checked={isDark}
            onCheckedChange={(v) => onToggleDark(Boolean(v))}
            aria-label="Toggle dark mode"
          />
        </div>
      </div>
    </div>
  )
}
