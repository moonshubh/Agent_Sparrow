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
import { MessageSquare, FolderGit2, FileText, Wrench, PanelLeft, Plus } from "lucide-react"

export type LeftTab = "primary" | "log" | "feedbacks" | "corrects"

type Props = {
  activeTab: LeftTab
  onChangeTab: (tab: LeftTab) => void
  onOpenRightSidebar: (anchorTop: number, anchorLeft?: number) => void
  onNewChat: () => void
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

export function AppSidebarLeft({ activeTab, onChangeTab, onOpenRightSidebar, onNewChat }: Props) {
  const { toggleSidebar } = useSidebar()
  return (
    <Sidebar side="left" variant="sidebar" collapsible="offcanvas" className="w-64 border-r">
      <SidebarHeader className="h-14 px-4 border-b flex-row items-center">
        <div className="flex items-center justify-between w-full">
          <div className="flex items-center gap-3">
            <Avatar className="h-10 w-10 rounded-xl bg-transparent overflow-hidden">
              <AvatarImage className="object-contain p-0.5" src="/agent_sparrow_logo.png" alt="Agent Sparrow" />
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
        <div className="p-2">
          <Button
            className="w-full h-9 justify-center"
            variant="default"
            onClick={onNewChat}
            aria-label="New Chat"
          >
            <Plus className="h-4 w-4" />
            <span className="ml-2">New Chat</span>
          </Button>
        </div>
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
