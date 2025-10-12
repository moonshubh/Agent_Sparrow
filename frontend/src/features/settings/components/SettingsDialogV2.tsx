"use client"

import React, { useMemo, useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/shared/ui/dialog"
import { Separator } from "@/shared/ui/separator"
import { cn } from "@/shared/lib/utils"
import { Settings, Key, User } from "lucide-react"
import { GeneralPanel } from "./panels/GeneralPanel"
import { APIKeysPanel } from "./panels/APIKeysPanel"
import { AccountPanel } from "./panels/AccountPanel"

type TabKey = "general" | "api-keys" | "account"

interface SettingsDialogV2Props {
  isOpen: boolean
  onClose: () => void
  defaultTab?: TabKey
}

type NavIcon = typeof Settings

const navItems: { id: TabKey; label: string; icon: NavIcon }[] = [
  { id: "general", label: "General", icon: Settings },
  { id: "api-keys", label: "API Keys", icon: Key },
  { id: "account", label: "Account", icon: User },
]

export function SettingsDialogV2({ isOpen, onClose, defaultTab = "general" }: SettingsDialogV2Props) {
  const [active, setActive] = useState<TabKey>(defaultTab)

  const Content = useMemo(() => {
    switch (active) {
      case "general":
        return <GeneralPanel />
      case "api-keys":
        return <APIKeysPanel />
      case "account":
        return <AccountPanel onClose={onClose} />
      default:
        return null
    }
  }, [active, onClose])

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-[900px] w-[900px] p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-3">
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5 text-accent" />
            Settings
          </DialogTitle>
        </DialogHeader>
        <Separator />
        <div className="flex h-[600px]">
          {/* Sidebar */}
          <aside className="w-56 border-r bg-background/60 py-2">
            <nav className="flex flex-col">
              {navItems.map(({ id, label, icon: Icon }) => {
                const isActive = active === id
                return (
                  <button
                    key={id}
                    onClick={() => setActive(id)}
                    className={cn(
                      "flex items-center gap-2 px-4 py-2 text-sm",
                      "hover:bg-secondary/50 transition-colors",
                      isActive && "text-accent bg-secondary/60"
                    )}
                    data-testid={`nav-${id}`}
                  >
                    <Icon className={cn("h-4 w-4", isActive && "text-accent")} />
                    {label}
                  </button>
                )
              })}
            </nav>
          </aside>

          {/* Content */}
          <section className="flex-1 min-w-0 p-6 overflow-y-auto">
            {Content}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  )
}
