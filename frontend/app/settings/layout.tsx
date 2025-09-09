"use client"

import React from 'react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Card } from '@/components/ui/card'
import { 
  Settings, 
  Key, 
  Gauge, 
  Database, 
  Shield, 
  User,
  Bell,
  Palette,
  Globe,
  Terminal
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { usePathname, useRouter } from 'next/navigation'

interface SettingsLayoutProps {
  children: React.ReactNode
}

const settingsTabs = [
  { id: 'general', label: 'General', icon: Settings, href: '/settings' },
  { id: 'api-keys', label: 'API Keys', icon: Key, href: '/settings/api-keys' },
  { id: 'rate-limits', label: 'Rate Limits', icon: Gauge, href: '/settings/rate-limits' },
  { id: 'sessions', label: 'Sessions', icon: Database, href: '/settings/sessions' },
  { id: 'security', label: 'Security', icon: Shield, href: '/settings/security' },
  { id: 'profile', label: 'Profile', icon: User, href: '/settings/profile' },
  { id: 'notifications', label: 'Notifications', icon: Bell, href: '/settings/notifications' },
  { id: 'appearance', label: 'Appearance', icon: Palette, href: '/settings/appearance' },
  { id: 'language', label: 'Language', icon: Globe, href: '/settings/language' },
  { id: 'developer', label: 'Developer', icon: Terminal, href: '/settings/developer' },
]

export default function SettingsLayout({ children }: SettingsLayoutProps) {
  const pathname = usePathname()
  const router = useRouter()
  
  // Determine active tab from pathname
  const activeTab = settingsTabs.find(tab => 
    pathname === tab.href || 
    (tab.href !== '/settings' && pathname.startsWith(tab.href))
  )?.id || 'general'

  const handleTabChange = (tabId: string) => {
    const tab = settingsTabs.find(t => t.id === tabId)
    if (tab) {
      router.push(tab.href)
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b backdrop-blur-xl bg-background/80 sticky top-0 z-10">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg glass-effect">
              <Settings className="h-5 w-5 text-accent" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">Settings</h1>
              <p className="text-sm text-muted-foreground">
                Manage your application preferences and configuration
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-6">
          {/* Tab Navigation */}
          <TabsList className="w-full justify-start flex-wrap h-auto p-1 glass-effect">
            {settingsTabs.map(tab => {
              const Icon = tab.icon
              const isActive = activeTab === tab.id
              
              return (
                <TabsTrigger
                  key={tab.id}
                  value={tab.id}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2.5",
                    "data-[state=active]:glass-effect",
                    "data-[state=active]:text-accent",
                    "hover:bg-secondary/50 transition-all duration-200"
                  )}
                >
                  <Icon className={cn(
                    "h-4 w-4",
                    isActive && "text-accent"
                  )} />
                  <span className="hidden sm:inline">{tab.label}</span>
                </TabsTrigger>
              )
            })}
          </TabsList>

          {/* Tab Content Area */}
          <Card className="glass-effect backdrop-blur-xl">
            <div className="p-6">
              {children}
            </div>
          </Card>
        </Tabs>
      </div>

      {/* Mobile Navigation */}
      <div className="fixed bottom-0 left-0 right-0 border-t bg-background/95 backdrop-blur-xl sm:hidden">
        <div className="flex items-center justify-around py-2">
          {settingsTabs.slice(0, 5).map(tab => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            
            return (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                className={cn(
                  "flex flex-col items-center gap-1 p-2 rounded-lg",
                  "hover:bg-secondary/50 transition-all duration-200",
                  isActive && "text-accent"
                )}
              >
                <Icon className="h-5 w-5" />
                <span className="text-[10px] font-medium">{tab.label}</span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}