"use client"

import React from "react"
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/shared/ui/sidebar"
import { Avatar, AvatarFallback, AvatarImage } from "@/shared/ui/avatar"
import { Button } from "@/shared/ui/button"
import { MessageSquare, FolderGit2, FileText, Wrench, PanelLeft } from "lucide-react"

export type LeftTab = "primary" | "log" | "feedbacks" | "corrects"

type Props = {
  activeTab: LeftTab
  onChangeTab: (tab: LeftTab) => void
  onOpenRightSidebar: (anchorTop: number, anchorLeft?: number) => void
}

const LEFT_ITEMS: Array<{
  id: LeftTab
  label: string
  Icon: React.ComponentType<{ className?: string }>
}> = [
  { id: "primary", label: "Primary Agent", Icon: MessageSquare },
  { id: "log", label: "Log Analysis", Icon: FolderGit2 },
  { id: "feedbacks", label: "Feedbacks", Icon: FileText },
  { id: "corrects", label: "Corrects", Icon: Wrench },
]

export function AppSidebarLeft({ activeTab, onChangeTab, onOpenRightSidebar }: Props) {
  const { toggleSidebar } = useSidebar()
  return (
    <Sidebar side="left" variant="sidebar" collapsible="offcanvas" className="w-64 border-r">
      <SidebarHeader className="px-3 py-3 border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Avatar className="h-9 w-9 rounded-xl">
              <AvatarImage src="/agent-sparrow-logo.png" alt="Agent Sparrow" />
              <AvatarFallback className="rounded-xl">AS</AvatarFallback>
            </Avatar>
            <div className="leading-tight">
              <div className="font-semibold">Agent Sparrow</div>
              <div className="text-xs text-muted-foreground">Mailbird Support</div>
            </div>
          </div>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            onClick={() => toggleSidebar()}
            title="Toggle left sidebar"
          >
            <PanelLeft className="h-4 w-4" />
          </Button>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {LEFT_ITEMS.map((item) => (
                <SidebarMenuItem key={item.id}>
                  <SidebarMenuButton
                    isActive={activeTab === item.id}
                    className="h-10 w-full"
                    onClick={(e) => {
                      onChangeTab(item.id)
                      const rect = (e.currentTarget as HTMLButtonElement).getBoundingClientRect()
                      const top = Math.max(64, Math.round(rect.top))
                      const left = Math.round(rect.right)
                      onOpenRightSidebar(top, left)
                    }}
                  >
                    <item.Icon className="h-4 w-4" />
                    <span className="truncate">{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  )
}

export default AppSidebarLeft
