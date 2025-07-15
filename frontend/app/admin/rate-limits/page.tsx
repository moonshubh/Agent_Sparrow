'use client';

import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { 
  Activity, 
  AlertTriangle, 
  RefreshCw, 
  Settings, 
  Shield, 
  Zap,
  Download,
  RotateCcw 
} from 'lucide-react';
import { RateLimitMetrics, RateLimitStatus } from '@/components/rate-limiting';
import { useRateLimiting } from '@/hooks/useRateLimiting';
import { toast } from 'sonner';

export default function RateLimitAdminPage() {
  const {
    status,
    loading,
    error,
    lastUpdated,
    isNearLimit,
    isCritical,
    blockedModels,
    refreshStatus,
    resetLimits,
    getWarningLevel,
  } = useRateLimiting({
    autoCheck: true,
    checkInterval: 15000, // 15 seconds for admin
    warningThreshold: 0.7,
    criticalThreshold: 0.85,
  });

  const [resetting, setResetting] = useState<string | null>(null);

  const handleResetLimits = async (model?: string) => {
    try {
      setResetting(model || 'all');
      const success = await resetLimits(model);
      if (success) {
        toast.success(
          model ? `Reset limits for ${model}` : 'Reset all limits',
          { description: 'Rate limits have been reset successfully' }
        );
      } else {
        toast.error('Failed to reset limits');
      }
    } catch (error) {
      toast.error('Failed to reset limits', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setResetting(null);
    }
  };

  const handleExportMetrics = async () => {
    try {
      if (!status) return;
      
      const data = {
        timestamp: new Date().toISOString(),
        status: status.status,
        usage_stats: status.details.usage_stats,
        utilization: status.details.utilization,
        health: status.details.health,
      };
      
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `rate-limit-metrics-${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      toast.success('Metrics exported successfully');
    } catch (error) {
      toast.error('Failed to export metrics');
    }
  };

  const warningLevel = getWarningLevel();

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Rate Limiting Dashboard</h1>
          <p className="text-muted-foreground">Monitor and manage Gemini API rate limits</p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge 
            variant={warningLevel === 'critical' ? 'destructive' : warningLevel === 'warning' ? 'secondary' : 'default'}
            className="text-sm"
          >
            <Shield className="h-3 w-3 mr-1" />
            {warningLevel === 'critical' ? 'Critical' : warningLevel === 'warning' ? 'Warning' : 'Healthy'}
          </Badge>
          <Button variant="outline" size="sm" onClick={refreshStatus} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={handleExportMetrics}>
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
        </div>
      </div>

      {/* Alert for Critical Status */}
      {isCritical && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            <strong>Critical:</strong> Rate limits are nearly exhausted. New requests may be blocked.
            {blockedModels.length > 0 && (
              <span className="ml-2">
                Blocked models: {blockedModels.join(', ')}
              </span>
            )}
          </AlertDescription>
        </Alert>
      )}

      {/* Warning for Near Limits */}
      {isNearLimit && !isCritical && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            <strong>Warning:</strong> Approaching rate limits. Monitor usage closely.
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="metrics">Detailed Metrics</TabsTrigger>
          <TabsTrigger value="controls">Admin Controls</TabsTrigger>
          <TabsTrigger value="config">Configuration</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Status Card */}
            <div className="lg:col-span-1">
              <RateLimitStatus 
                className="h-fit"
                showDetails={true}
                autoUpdate={false}
              />
            </div>
            
            {/* Quick Stats */}
            <div className="lg:col-span-2 space-y-4">
              {status && (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <Card>
                      <CardContent className="p-4">
                        <div className="flex items-center space-x-2">
                          <Activity className="h-4 w-4 text-blue-500" />
                          <div>
                            <div className="text-2xl font-bold">{status.details.usage_stats.total_requests_today}</div>
                            <div className="text-xs text-gray-500">Requests Today</div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="p-4">
                        <div className="flex items-center space-x-2">
                          <Zap className="h-4 w-4 text-blue-500" />
                          <div>
                            <div className="text-2xl font-bold">
                              {status.details.usage_stats.flash_stats.rpm_used}
                            </div>
                            <div className="text-xs text-gray-500">Flash RPM</div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="p-4">
                        <div className="flex items-center space-x-2">
                          <Zap className="h-4 w-4 text-mb-blue-500" />
                          <div>
                            <div className="text-2xl font-bold">
                              {status.details.usage_stats.pro_stats.rpm_used}
                            </div>
                            <div className="text-xs text-gray-500">Pro RPM</div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="p-4">
                        <div className="flex items-center space-x-2">
                          <Shield className="h-4 w-4 text-green-500" />
                          <div>
                            <div className="text-2xl font-bold">
                              {Math.round(status.details.usage_stats.uptime_percentage)}%
                            </div>
                            <div className="text-xs text-gray-500">Uptime</div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </div>

                  {/* System Status */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">System Status</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="space-y-2">
                          <div className="text-sm font-medium">Circuit Breakers</div>
                          <div className="space-y-1">
                            <div className="flex justify-between items-center">
                              <span className="text-sm">Flash</span>
                              <Badge variant={status.details.usage_stats.flash_circuit.state === 'closed' ? 'default' : 'destructive'}>
                                {status.details.usage_stats.flash_circuit.state}
                              </Badge>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-sm">Pro</span>
                              <Badge variant={status.details.usage_stats.pro_circuit.state === 'closed' ? 'default' : 'destructive'}>
                                {status.details.usage_stats.pro_circuit.state}
                              </Badge>
                            </div>
                          </div>
                        </div>
                        <div className="space-y-2">
                          <div className="text-sm font-medium">Health Status</div>
                          <div className="space-y-1">
                            <div className="flex justify-between items-center">
                              <span className="text-sm">Overall</span>
                              <Badge variant={status.details.health.overall === 'healthy' ? 'default' : 'destructive'}>
                                {status.details.health.overall}
                              </Badge>
                            </div>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </>
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="metrics" className="space-y-4">
          <RateLimitMetrics 
            adminMode={true}
            autoRefresh={true}
            refreshInterval={15000}
          />
        </TabsContent>

        <TabsContent value="controls" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Settings className="h-5 w-5" />
                <span>Administrative Controls</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Reset Controls */}
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-medium mb-2">Reset Rate Limits</h3>
                  <p className="text-sm text-muted-foreground mb-4">
                    Use these controls to reset rate limits in development or emergency situations.
                    <strong className="text-destructive"> Use with caution in production.</strong>
                  </p>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button 
                        variant="outline" 
                        className="w-full"
                        disabled={resetting !== null}
                      >
                        <RotateCcw className="h-4 w-4 mr-2" />
                        Reset Flash Limits
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Reset Flash Model Limits?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will reset the rate limits for the Gemini 2.5 Flash model.
                          This action should only be used in development or emergency situations.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction 
                          onClick={() => handleResetLimits('gemini-2.5-flash')}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          {resetting === 'gemini-2.5-flash' ? 'Resetting...' : 'Reset Flash'}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>

                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button 
                        variant="outline" 
                        className="w-full"
                        disabled={resetting !== null}
                      >
                        <RotateCcw className="h-4 w-4 mr-2" />
                        Reset Pro Limits
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Reset Pro Model Limits?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will reset the rate limits for the Gemini 2.5 Pro model.
                          This action should only be used in development or emergency situations.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction 
                          onClick={() => handleResetLimits('gemini-2.5-pro')}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          {resetting === 'gemini-2.5-pro' ? 'Resetting...' : 'Reset Pro'}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>

                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button 
                        variant="destructive" 
                        className="w-full"
                        disabled={resetting !== null}
                      >
                        <RotateCcw className="h-4 w-4 mr-2" />
                        Reset All Limits
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Reset All Rate Limits?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will reset the rate limits for ALL models.
                          This action should only be used in development or emergency situations.
                          <strong className="block mt-2 text-destructive">
                            This is a destructive action and cannot be undone.
                          </strong>
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction 
                          onClick={() => handleResetLimits()}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          {resetting === 'all' ? 'Resetting...' : 'Reset All'}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>

              {/* Safety Information */}
              <Alert>
                <Shield className="h-4 w-4" />
                <AlertDescription>
                  <strong>Safety Information:</strong> Rate limits are designed to keep the service within 
                  Google's free tier. Resetting limits should only be done during development or in 
                  emergency situations where you understand the implications.
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="config" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Rate Limiting Configuration</CardTitle>
            </CardHeader>
            <CardContent>
              {status && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-4">
                    <h3 className="font-medium">Gemini 2.5 Flash</h3>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span>RPM Limit:</span>
                        <span className="font-mono">{status.details.usage_stats.flash_stats.rpm_limit}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>RPD Limit:</span>
                        <span className="font-mono">{status.details.usage_stats.flash_stats.rpd_limit}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Safety Margin:</span>
                        <span className="font-mono">{Math.round(status.details.usage_stats.flash_stats.safety_margin * 100)}%</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="space-y-4">
                    <h3 className="font-medium">Gemini 2.5 Pro</h3>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span>RPM Limit:</span>
                        <span className="font-mono">{status.details.usage_stats.pro_stats.rpm_limit}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>RPD Limit:</span>
                        <span className="font-mono">{status.details.usage_stats.pro_stats.rpd_limit}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Safety Margin:</span>
                        <span className="font-mono">{Math.round(status.details.usage_stats.pro_stats.safety_margin * 100)}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Footer Info */}
      <div className="text-xs text-muted-foreground text-center">
        {lastUpdated && `Last updated: ${lastUpdated.toLocaleString()}`}
        {error && (
          <div className="text-destructive mt-2">
            Error: {error}
          </div>
        )}
      </div>
    </div>
  );
}