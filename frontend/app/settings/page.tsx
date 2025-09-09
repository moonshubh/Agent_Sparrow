"use client"

import React, { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, Settings, Palette, Bell, Lock, Monitor } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { toast } from 'sonner'

// Settings interface for type safety
interface SettingsState {
  darkMode: boolean
  compactMode: boolean
  desktopNotifications: boolean
  soundAlerts: boolean
  autoLogout: boolean
  analytics: boolean
  hardwareAcceleration: boolean
  autoUpdate: boolean
}

// Default settings
const defaultSettings: SettingsState = {
  darkMode: false,
  compactMode: false,
  desktopNotifications: false,
  soundAlerts: false,
  autoLogout: true,
  analytics: false,
  hardwareAcceleration: true,
  autoUpdate: true,
}

// Settings validation function
function validateSettings(data: unknown): Partial<SettingsState> {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return {}
  }
  
  const validatedSettings: Partial<SettingsState> = {}
  const obj = data as Record<string, unknown>
  
  // Validate each setting property
  const settingsKeys: (keyof SettingsState)[] = [
    'darkMode', 'compactMode', 'desktopNotifications', 'soundAlerts',
    'autoLogout', 'analytics', 'hardwareAcceleration', 'autoUpdate'
  ]
  
  for (const key of settingsKeys) {
    if (key in obj && typeof obj[key] === 'boolean') {
      validatedSettings[key] = obj[key] as boolean
    }
  }
  
  return validatedSettings
}

export default function SettingsPage() {
  const router = useRouter()
  const [settings, setSettings] = useState<SettingsState>(defaultSettings)
  const [isLoading, setIsLoading] = useState(true)

  // Load settings from localStorage on component mount
  useEffect(() => {
    try {
      const savedSettings = localStorage.getItem('mb-sparrow-settings')
      if (savedSettings) {
        const parsedData = JSON.parse(savedSettings)
        const validatedSettings = validateSettings(parsedData)
        
        // Only merge validated settings
        if (Object.keys(validatedSettings).length > 0) {
          setSettings(prev => ({ ...prev, ...validatedSettings }))
        } else {
          console.warn('No valid settings found in localStorage, using defaults')
          // Optionally notify user of invalid data
          if (process.env.NODE_ENV === 'development') {
            toast.error('Invalid settings data found, using defaults')
          }
        }
      }
    } catch (error) {
      console.error('Failed to load settings:', error)
      toast.error('Failed to load saved settings. Using default settings.')
      
      // Clear corrupted data
      try {
        localStorage.removeItem('mb-sparrow-settings')
      } catch (cleanupError) {
        console.error('Failed to clear corrupted settings:', cleanupError)
      }
    } finally {
      setIsLoading(false)
    }
  }, [])

  // Save settings to localStorage whenever settings change
  useEffect(() => {
    if (!isLoading) {
      try {
        localStorage.setItem('mb-sparrow-settings', JSON.stringify(settings))
      } catch (error) {
        console.error('Failed to save settings:', error)
        toast.error('Failed to save settings')
      }
    }
  }, [settings, isLoading])

  // Settings display names mapping (defined once for performance)
  const settingNames: Record<keyof SettingsState, string> = {
    darkMode: 'Dark Mode',
    compactMode: 'Compact Mode',
    desktopNotifications: 'Desktop Notifications',
    soundAlerts: 'Sound Alerts',
    autoLogout: 'Auto-logout',
    analytics: 'Analytics',
    hardwareAcceleration: 'Hardware Acceleration',
    autoUpdate: 'Auto-update',
  }

  // Generic handler for settings changes
  const handleSettingChange = (key: keyof SettingsState, value: boolean) => {
    setSettings(prev => ({ ...prev, [key]: value }))
    
    // Show success feedback
    toast.success(`${settingNames[key]} ${value ? 'enabled' : 'disabled'}`)
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card/50 backdrop-blur">
        <div className="container max-w-4xl mx-auto px-6 py-4">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.back()}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            <div className="flex items-center gap-3">
              <Settings className="h-6 w-6 text-accent" />
              <div>
                <h1 className="text-2xl font-bold">Settings</h1>
                <p className="text-sm text-muted-foreground">
                  Customize your MB-Sparrow experience
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="container max-w-4xl mx-auto px-6 py-8">
        <div className="space-y-8">
          {/* Appearance */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette className="h-5 w-5 text-accent" />
                Appearance
              </CardTitle>
              <CardDescription>
                Customize the visual appearance of MB-Sparrow
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label 
                    htmlFor="dark-mode-switch" 
                    className="text-base cursor-pointer"
                  >
                    Dark Mode
                  </Label>
                  <div className="text-sm text-muted-foreground">
                    Switch between light and dark themes
                  </div>
                </div>
                <Switch 
                  id="dark-mode-switch"
                  checked={settings.darkMode}
                  onCheckedChange={(checked) => handleSettingChange('darkMode', checked)}
                  aria-label="Toggle dark mode"
                />
              </div>
              
              <Separator />
              
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label 
                    htmlFor="compact-mode-switch" 
                    className="text-base cursor-pointer"
                  >
                    Compact Mode
                  </Label>
                  <div className="text-sm text-muted-foreground">
                    Reduce spacing for more content on screen
                  </div>
                </div>
                <Switch 
                  id="compact-mode-switch"
                  checked={settings.compactMode}
                  onCheckedChange={(checked) => handleSettingChange('compactMode', checked)}
                  aria-label="Toggle compact mode"
                />
              </div>
            </CardContent>
          </Card>

          {/* Notifications */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5 text-accent" />
                Notifications
              </CardTitle>
              <CardDescription>
                Control how and when you receive notifications
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label 
                    htmlFor="desktop-notifications-switch" 
                    className="text-base cursor-pointer"
                  >
                    Desktop Notifications
                  </Label>
                  <div className="text-sm text-muted-foreground">
                    Show notifications when new messages arrive
                  </div>
                </div>
                <Switch 
                  id="desktop-notifications-switch"
                  checked={settings.desktopNotifications}
                  onCheckedChange={(checked) => handleSettingChange('desktopNotifications', checked)}
                  aria-label="Toggle desktop notifications"
                />
              </div>
              
              <Separator />
              
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label 
                    htmlFor="sound-alerts-switch" 
                    className="text-base cursor-pointer"
                  >
                    Sound Alerts
                  </Label>
                  <div className="text-sm text-muted-foreground">
                    Play sound when receiving notifications
                  </div>
                </div>
                <Switch 
                  id="sound-alerts-switch"
                  checked={settings.soundAlerts}
                  onCheckedChange={(checked) => handleSettingChange('soundAlerts', checked)}
                  aria-label="Toggle sound alerts"
                />
              </div>
            </CardContent>
          </Card>

          {/* Privacy & Security */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Lock className="h-5 w-5 text-accent" />
                Privacy & Security
              </CardTitle>
              <CardDescription>
                Manage your privacy and security preferences
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label 
                    htmlFor="auto-logout-switch" 
                    className="text-base cursor-pointer"
                  >
                    Auto-logout
                  </Label>
                  <div className="text-sm text-muted-foreground">
                    Automatically sign out after 24 hours of inactivity
                  </div>
                </div>
                <Switch 
                  id="auto-logout-switch"
                  checked={settings.autoLogout}
                  onCheckedChange={(checked) => handleSettingChange('autoLogout', checked)}
                  aria-label="Toggle auto-logout"
                />
              </div>
              
              <Separator />
              
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label 
                    htmlFor="analytics-switch" 
                    className="text-base cursor-pointer"
                  >
                    Analytics
                  </Label>
                  <div className="text-sm text-muted-foreground">
                    Help improve MB-Sparrow by sharing anonymous usage data
                  </div>
                </div>
                <Switch 
                  id="analytics-switch"
                  checked={settings.analytics}
                  onCheckedChange={(checked) => handleSettingChange('analytics', checked)}
                  aria-label="Toggle analytics"
                />
              </div>
            </CardContent>
          </Card>

          {/* System */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Monitor className="h-5 w-5 text-accent" />
                System
              </CardTitle>
              <CardDescription>
                System-level preferences and performance options
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label 
                    htmlFor="hardware-acceleration-switch" 
                    className="text-base cursor-pointer"
                  >
                    Hardware Acceleration
                  </Label>
                  <div className="text-sm text-muted-foreground">
                    Use GPU acceleration for better performance
                  </div>
                </div>
                <Switch 
                  id="hardware-acceleration-switch"
                  checked={settings.hardwareAcceleration}
                  onCheckedChange={(checked) => handleSettingChange('hardwareAcceleration', checked)}
                  aria-label="Toggle hardware acceleration"
                />
              </div>
              
              <Separator />
              
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label 
                    htmlFor="auto-update-switch" 
                    className="text-base cursor-pointer"
                  >
                    Auto-update
                  </Label>
                  <div className="text-sm text-muted-foreground">
                    Automatically download and install updates
                  </div>
                </div>
                <Switch 
                  id="auto-update-switch"
                  checked={settings.autoUpdate}
                  onCheckedChange={(checked) => handleSettingChange('autoUpdate', checked)}
                  aria-label="Toggle auto-update"
                />
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}