"use client"

import React, { useState, useEffect } from 'react'
import { SessionStatusChip } from '@/components/sessions/SessionStatusChip'
import { AutoSaveIndicator, useAutoSave } from '@/components/sessions/AutoSaveIndicator'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  Database,
  Trash2,
  Download,
  Upload,
  Clock,
  MessageSquare,
  User,
  Calendar,
  Activity,
  RefreshCw,
  Save,
  Archive,
  AlertCircle,
  CheckCircle,
  XCircle,
  Info,
  Settings
} from 'lucide-react'
import { sessionsAPI, type ChatSession, type AgentType } from '@/lib/api/sessions'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

interface SessionStats {
  totalSessions: number
  primarySessions: number
  logAnalysisSessions: number
  researchSessions: number
  totalMessages: number
  oldestSession?: Date
  newestSession?: Date
}

export default function SessionsSettingsPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedSession, setSelectedSession] = useState<ChatSession | null>(null)
  const [stats, setStats] = useState<SessionStats>({
    totalSessions: 0,
    primarySessions: 0,
    logAnalysisSessions: 0,
    researchSessions: 0,
    totalMessages: 0
  })
  const [settings, setSettings] = useState({
    autoSave: true,
    sessionTimeout: 24,
    maxSessions: 100,
    compressOldSessions: true
  })

  // Auto-save settings
  const { saveStatus, lastSaved } = useAutoSave(
    async () => {
      localStorage.setItem('session-settings', JSON.stringify(settings))
    },
    [settings],
    1000
  )

  useEffect(() => {
    fetchSessions()
    loadSettings()
  }, [])

  useEffect(() => {
    calculateStats()
  }, [sessions])

  const loadSettings = () => {
    const saved = localStorage.getItem('session-settings')
    if (saved) {
      try {
        setSettings(JSON.parse(saved))
      } catch (error) {
        console.error('Failed to load settings:', error)
      }
    }
  }

  const fetchSessions = async () => {
    try {
      setLoading(true)
      const sessionList = await sessionsAPI.list(100, 0)
      setSessions(sessionList)
    } catch (error) {
      console.error('Failed to fetch sessions:', error)
      toast.error('Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }

  const calculateStats = () => {
    const primary = sessions.filter(s => s.agent_type === 'primary').length
    const logAnalysis = sessions.filter(s => s.agent_type === 'log_analysis').length
    const research = sessions.filter(s => s.agent_type === 'research').length
    
    const dates = sessions
      .map(s => s.created_at ? new Date(s.created_at) : null)
      .filter(d => d !== null) as Date[]
    
    setStats({
      totalSessions: sessions.length,
      primarySessions: primary,
      logAnalysisSessions: logAnalysis,
      researchSessions: research,
      totalMessages: 0, // Would need to fetch messages for each session
      oldestSession: dates.length > 0 ? new Date(Math.min(...dates.map(d => d.getTime()))) : undefined,
      newestSession: dates.length > 0 ? new Date(Math.max(...dates.map(d => d.getTime()))) : undefined
    })
  }

  const handleDeleteSession = async (sessionId: string) => {
    const confirmed = window.confirm('Are you sure you want to delete this session? This action cannot be undone.')
    if (!confirmed) return

    try {
      await sessionsAPI.remove(sessionId)
      toast.success('Session deleted successfully')
      fetchSessions()
      if (selectedSession?.id === sessionId) {
        setSelectedSession(null)
      }
    } catch (error) {
      toast.error('Failed to delete session')
    }
  }

  const handleDeleteAllSessions = async () => {
    const confirmed = window.confirm('Are you sure you want to delete ALL sessions? This action cannot be undone.')
    if (!confirmed) return

    try {
      for (const session of sessions) {
        await sessionsAPI.remove(session.id)
      }
      toast.success('All sessions deleted successfully')
      setSessions([])
      setSelectedSession(null)
    } catch (error) {
      toast.error('Failed to delete sessions')
    }
  }

  const handleExportSessions = () => {
    const dataStr = JSON.stringify(sessions, null, 2)
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr)
    const exportFileDefaultName = `sessions-${new Date().toISOString().split('T')[0]}.json`
    
    const linkElement = document.createElement('a')
    linkElement.setAttribute('href', dataUri)
    linkElement.setAttribute('download', exportFileDefaultName)
    linkElement.click()
    
    toast.success('Sessions exported successfully')
  }

  const getAgentIcon = (agentType?: AgentType) => {
    switch (agentType) {
      case 'log_analysis':
        return <Activity className="h-4 w-4" />
      case 'research':
        return <MessageSquare className="h-4 w-4" />
      default:
        return <User className="h-4 w-4" />
    }
  }

  const getAgentColor = (agentType?: AgentType) => {
    switch (agentType) {
      case 'log_analysis':
        return 'text-blue-500 bg-blue-500/10 border-blue-500/30'
      case 'research':
        return 'text-purple-500 bg-purple-500/10 border-purple-500/30'
      default:
        return 'text-green-500 bg-green-500/10 border-green-500/30'
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Database className="h-5 w-5 text-accent" />
            Session Management
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Manage your chat sessions and conversation history
          </p>
        </div>
        <div className="flex items-center gap-2">
          <AutoSaveIndicator status={saveStatus} lastSaved={lastSaved} />
          <Button
            variant="outline"
            size="sm"
            onClick={fetchSessions}
            className="glass-effect"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <Separator />

      {/* Statistics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="glass-effect">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Total Sessions</p>
                <p className="text-2xl font-bold">{stats.totalSessions}</p>
              </div>
              <Database className="h-8 w-8 text-accent opacity-20" />
            </div>
          </CardContent>
        </Card>
        
        <Card className="glass-effect">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Primary Agent</p>
                <p className="text-2xl font-bold">{stats.primarySessions}</p>
              </div>
              <User className="h-8 w-8 text-green-500 opacity-20" />
            </div>
          </CardContent>
        </Card>
        
        <Card className="glass-effect">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Log Analysis</p>
                <p className="text-2xl font-bold">{stats.logAnalysisSessions}</p>
              </div>
              <Activity className="h-8 w-8 text-blue-500 opacity-20" />
            </div>
          </CardContent>
        </Card>
        
        <Card className="glass-effect">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Research</p>
                <p className="text-2xl font-bold">{stats.researchSessions}</p>
              </div>
              <MessageSquare className="h-8 w-8 text-purple-500 opacity-20" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Sessions List */}
      <Card className="glass-effect">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Active Sessions</CardTitle>
              <CardDescription>Your recent chat sessions</CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportSessions}
                disabled={sessions.length === 0}
                className="glass-effect"
              >
                <Download className="h-4 w-4 mr-2" />
                Export
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDeleteAllSessions}
                disabled={sessions.length === 0}
                className="glass-effect text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Clear All
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-16 bg-secondary/20 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : sessions.length === 0 ? (
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                No sessions found. Start a new chat to create your first session.
              </AlertDescription>
            </Alert>
          ) : (
            <ScrollArea className="h-[400px]">
              <div className="space-y-2">
                {sessions.map(session => (
                  <div
                    key={session.id}
                    className={cn(
                      "flex items-center justify-between p-3 rounded-lg border glass-effect",
                      "hover:scale-[1.01] transition-all duration-200 cursor-pointer",
                      selectedSession?.id === session.id && "ring-2 ring-accent"
                    )}
                    onClick={() => setSelectedSession(session)}
                  >
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "p-2 rounded-lg",
                        getAgentColor(session.agent_type)
                      )}>
                        {getAgentIcon(session.agent_type)}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">
                            {session.title || `Session ${session.id.slice(0, 8)}`}
                          </span>
                          <Badge variant="outline" className="text-xs glass-effect">
                            {session.agent_type || 'primary'}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-4 mt-1">
                          <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            {session.created_at ? new Date(session.created_at).toLocaleDateString() : 'Unknown'}
                          </span>
                          <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {session.updated_at ? new Date(session.updated_at).toLocaleTimeString() : 'Unknown'}
                          </span>
                        </div>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDeleteSession(session.id)
                      }}
                      className="text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {/* Session Settings */}
      <Card className="glass-effect">
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Session Settings
          </CardTitle>
          <CardDescription>Configure session behavior</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="auto-save">Auto-save Sessions</Label>
              <p className="text-xs text-muted-foreground">
                Automatically save session data as you chat
              </p>
            </div>
            <Switch
              id="auto-save"
              checked={settings.autoSave}
              onCheckedChange={(checked) => setSettings(prev => ({ ...prev, autoSave: checked }))}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor="compress">Compress Old Sessions</Label>
              <p className="text-xs text-muted-foreground">
                Compress sessions older than 30 days to save space
              </p>
            </div>
            <Switch
              id="compress"
              checked={settings.compressOldSessions}
              onCheckedChange={(checked) => setSettings(prev => ({ ...prev, compressOldSessions: checked }))}
            />
          </div>

          <Separator />

          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>
              Sessions are automatically saved and can be accessed across devices when logged in.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    </div>
  )
}