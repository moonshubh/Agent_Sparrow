/**
 * PDF Storage Analytics Component
 * Displays metrics and analytics for PDF storage and cleanup
 */

'use client'

import React, { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { 
  Database, 
  HardDrive, 
  FileText, 
  CheckCircle, 
  Clock, 
  TrendingDown,
  RefreshCw,
  Info,
  Loader2,
  Trash2
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useToast } from '@/hooks/use-toast'
import { formatDistanceToNow } from 'date-fns'

interface PDFStorageStats {
  pending_cleanup: number
  cleaned_count: number
  total_mb_freed: number
  avg_pdf_size_mb: number
  total_pdf_conversations: number
  timestamp?: string
}

interface PDFStorageAnalyticsProps {
  onTriggerCleanup?: () => void
  className?: string
}

export function PDFStorageAnalytics({ onTriggerCleanup, className }: PDFStorageAnalyticsProps) {
  const [stats, setStats] = useState<PDFStorageStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isCleanupRunning, setIsCleanupRunning] = useState(false)
  const { toast } = useToast()

  const fetchStats = async () => {
    try {
      const response = await fetch('/api/v1/feedme/analytics/pdf-storage')
      if (!response.ok) throw new Error('Failed to fetch stats')
      
      const data = await response.json()
      setStats(data)
    } catch (error) {
      console.error('Error fetching PDF storage stats:', error)
      toast({
        title: 'Error',
        description: 'Failed to load PDF storage analytics',
        variant: 'destructive'
      })
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
    // Refresh every 30 seconds
    const interval = setInterval(fetchStats, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleTriggerCleanup = async () => {
    setIsCleanupRunning(true)
    try {
      const response = await fetch('/api/v1/feedme/cleanup/pdfs/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit: 100 })
      })
      
      if (!response.ok) throw new Error('Failed to trigger cleanup')
      
      const result = await response.json()
      toast({
        title: 'Cleanup Started',
        description: result.message || 'PDF cleanup task has been scheduled',
      })
      
      // Refresh stats after a delay
      setTimeout(fetchStats, 5000)
      
      if (onTriggerCleanup) {
        onTriggerCleanup()
      }
    } catch (error) {
      console.error('Error triggering cleanup:', error)
      toast({
        title: 'Error',
        description: 'Failed to trigger PDF cleanup',
        variant: 'destructive'
      })
    } finally {
      setIsCleanupRunning(false)
    }
  }

  if (isLoading && !stats) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center h-32">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  const storageUsedMB = stats ? (stats.total_pdf_conversations * stats.avg_pdf_size_mb) - stats.total_mb_freed : 0
  const potentialSavingsMB = stats ? stats.pending_cleanup * stats.avg_pdf_size_mb : 0
  const savingsPercentage = stats && stats.total_pdf_conversations > 0 
    ? (stats.cleaned_count / stats.total_pdf_conversations) * 100 
    : 0

  return (
    <div className={cn("space-y-4", className)}>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Database className="h-5 w-5" />
              PDF Storage Analytics
            </CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchStats}
              disabled={isLoading}
            >
              <RefreshCw className={cn("h-4 w-4 mr-1", isLoading && "animate-spin")} />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {stats && (
            <>
              {/* Storage Overview */}
              <div className="grid gap-4 md:grid-cols-3">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Total PDFs
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-baseline gap-2">
                      <span className="text-2xl font-bold">{stats.total_pdf_conversations}</span>
                      <FileText className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Storage Freed
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-baseline gap-2">
                      <span className="text-2xl font-bold">{stats.total_mb_freed.toFixed(1)}</span>
                      <span className="text-sm text-muted-foreground">MB</span>
                      <TrendingDown className="h-4 w-4 text-green-600" />
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Avg PDF Size
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-baseline gap-2">
                      <span className="text-2xl font-bold">{stats.avg_pdf_size_mb.toFixed(1)}</span>
                      <span className="text-sm text-muted-foreground">MB</span>
                      <HardDrive className="h-4 w-4 text-muted-foreground" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Cleanup Status */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium">Cleanup Progress</h3>
                  <Badge variant="outline">
                    {savingsPercentage.toFixed(0)}% Optimized
                  </Badge>
                </div>
                
                <Progress value={savingsPercentage} className="h-2" />
                
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                    <span>{stats.cleaned_count} Cleaned</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 text-yellow-600" />
                    <span>{stats.pending_cleanup} Pending</span>
                  </div>
                </div>
              </div>

              {/* Potential Savings Alert */}
              {stats.pending_cleanup > 0 && (
                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertTitle>Storage Optimization Available</AlertTitle>
                  <AlertDescription className="space-y-2">
                    <p>
                      You have {stats.pending_cleanup} approved PDFs that can be cleaned up, 
                      potentially saving {potentialSavingsMB.toFixed(1)} MB of storage.
                    </p>
                    <Button
                      size="sm"
                      onClick={handleTriggerCleanup}
                      disabled={isCleanupRunning}
                      className="mt-2"
                    >
                      {isCleanupRunning ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                          Running Cleanup...
                        </>
                      ) : (
                        <>
                          <Trash2 className="h-4 w-4 mr-1" />
                          Run Cleanup Now
                        </>
                      )}
                    </Button>
                  </AlertDescription>
                </Alert>
              )}

              {/* Last Updated */}
              {stats.timestamp && (
                <div className="text-xs text-muted-foreground text-right">
                  Last updated {formatDistanceToNow(new Date(stats.timestamp), { addSuffix: true })}
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default PDFStorageAnalytics