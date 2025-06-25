"use client"

import React, { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { 
  Lightbulb,
  Shield,
  Eye,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  Settings
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface EnhancedRecommendationsCardProps {
  immediateActions: string[]
  preventiveMeasures: string[]
  monitoringRecommendations: string[]
  automatedRemediationAvailable: boolean
  className?: string
}

export function EnhancedRecommendationsCard({ 
  immediateActions,
  preventiveMeasures,
  monitoringRecommendations,
  automatedRemediationAvailable,
  className 
}: EnhancedRecommendationsCardProps) {
  const [expandedSection, setExpandedSection] = useState<string | null>(null)

  const toggleSection = (section: string) => {
    setExpandedSection(expandedSection === section ? null : section)
  }

  const hasAnyRecommendations = 
    immediateActions?.length > 0 || 
    preventiveMeasures?.length > 0 || 
    monitoringRecommendations?.length > 0

  if (!hasAnyRecommendations) {
    return (
      <Card className={cn("w-full", className)}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Lightbulb className="h-4 w-4 text-primary" />
            Recommendations
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4 text-muted-foreground">
            <CheckCircle className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No specific recommendations</p>
            <p className="text-xs mt-1">System appears to be functioning normally</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn("w-full", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Lightbulb className="h-4 w-4 text-primary" />
          Recommendations
          {automatedRemediationAvailable && (
            <Badge variant="secondary" className="ml-auto text-xs">
              <Settings className="h-3 w-3 mr-1" />
              Automation Available
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Automation Status */}
        {automatedRemediationAvailable && (
          <Alert className="ring-1 ring-blue-500/40 bg-blue-900/20 border-blue-500/30">
            <Settings className="h-4 w-4 text-blue-600 dark:text-blue-400" />
            <AlertDescription className="text-sm text-blue-700 dark:text-blue-300">
              <span className="font-semibold">Automated Remediation Available:</span>
              <div className="mt-1 text-xs">
                Some solutions can be automatically applied with user confirmation.
              </div>
            </AlertDescription>
          </Alert>
        )}

        {/* Immediate Actions */}
        {immediateActions && immediateActions.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-red-500" />
                Immediate Actions ({immediateActions.length})
              </h4>
              {immediateActions.length > 3 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleSection('immediate')}
                  className="text-xs h-auto p-1"
                >
                  {expandedSection === 'immediate' ? (
                    <>
                      <ChevronUp className="h-3 w-3 mr-1" />
                      Show Less
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-3 w-3 mr-1" />
                      Show All
                    </>
                  )}
                </Button>
              )}
            </div>

            <div className="space-y-2">
              {(expandedSection === 'immediate' ? immediateActions : immediateActions.slice(0, 3))
                .map((action, index) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg bg-red-500/10 border border-red-500/20"
                  >
                    <div className="flex items-start gap-2">
                      <div className="w-5 h-5 rounded-full bg-red-500/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <span className="text-xs font-semibold text-red-600 dark:text-red-400">
                          {index + 1}
                        </span>
                      </div>
                      <div className="text-sm text-foreground/90">
                        {action}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Preventive Measures */}
        {preventiveMeasures && preventiveMeasures.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Shield className="h-4 w-4 text-blue-500" />
                Preventive Measures ({preventiveMeasures.length})
              </h4>
              {preventiveMeasures.length > 3 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleSection('preventive')}
                  className="text-xs h-auto p-1"
                >
                  {expandedSection === 'preventive' ? (
                    <>
                      <ChevronUp className="h-3 w-3 mr-1" />
                      Show Less
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-3 w-3 mr-1" />
                      Show All
                    </>
                  )}
                </Button>
              )}
            </div>

            <div className="space-y-2">
              {(expandedSection === 'preventive' ? preventiveMeasures : preventiveMeasures.slice(0, 3))
                .map((measure, index) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20"
                  >
                    <div className="flex items-start gap-2">
                      <Shield className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                      <div className="text-sm text-foreground/90">
                        {measure}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Monitoring Recommendations */}
        {monitoringRecommendations && monitoringRecommendations.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Eye className="h-4 w-4 text-green-500" />
                Monitoring Recommendations ({monitoringRecommendations.length})
              </h4>
              {monitoringRecommendations.length > 3 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => toggleSection('monitoring')}
                  className="text-xs h-auto p-1"
                >
                  {expandedSection === 'monitoring' ? (
                    <>
                      <ChevronUp className="h-3 w-3 mr-1" />
                      Show Less
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-3 w-3 mr-1" />
                      Show All
                    </>
                  )}
                </Button>
              )}
            </div>

            <div className="space-y-2">
              {(expandedSection === 'monitoring' ? monitoringRecommendations : monitoringRecommendations.slice(0, 3))
                .map((recommendation, index) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg bg-green-500/10 border border-green-500/20"
                  >
                    <div className="flex items-start gap-2">
                      <Eye className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                      <div className="text-sm text-foreground/90">
                        {recommendation}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}