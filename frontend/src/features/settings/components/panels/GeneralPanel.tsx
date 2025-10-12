"use client"

import React, { useEffect, useState } from "react"
import { useTheme } from "next-themes"
import { Label } from "@/shared/ui/label"
import { RadioGroup, RadioGroupItem } from "@/shared/ui/radio-group"
import { Separator } from "@/shared/ui/separator"

export function GeneralPanel() {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  // Keep a stable selected value once mounted
  const selected = mounted ? (theme === "system" ? resolvedTheme : theme) : "light"

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">General</h2>
        <p className="text-sm text-muted-foreground">Basic preferences for appearance.</p>
      </div>

      <Separator />

      <div className="grid gap-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">Theme</div>
            <div className="text-xs text-muted-foreground">Choose Light or Dark.</div>
          </div>
          <div>
            <RadioGroup
              value={selected === "dark" ? "dark" : "light"}
              onValueChange={(v) => setTheme(v)}
              className="flex items-center gap-4"
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem id="theme-light" value="light" />
                <Label htmlFor="theme-light">Light</Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem id="theme-dark" value="dark" />
                <Label htmlFor="theme-dark">Dark</Label>
              </div>
            </RadioGroup>
          </div>
        </div>
      </div>
    </div>
  )
}

