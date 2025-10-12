'use client'

import { useState } from 'react'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'
import { Progress } from '@/shared/ui/progress'
import { Textarea } from '@/shared/ui/textarea'
import { Alert, AlertDescription } from '@/shared/ui/alert'
import {
  PlayCircle,
  CheckCircle,
  XCircle,
  SkipForward,
  AlertTriangle,
  ChevronRight,
  Activity,
  ClipboardCheck,
  MessageSquare,
  Zap,
  Shield,
  Target
} from 'lucide-react'

export interface DiagnosticStep {
  id: string
  name: string
  description: string
  expected_outcome?: string
  time_estimate?: string
  complexity?: string
  requires_customer_action?: boolean
  verification?: string
}

export interface VerificationCheckpoint {
  checkpoints_passed?: string[]
  current_verification?: string
}

export interface TroubleshootingState {
  session_id?: string
  current_phase?: string
  current_step?: DiagnosticStep
  next_steps?: DiagnosticStep[]
  progress_percentage?: number
  verification_status?: VerificationCheckpoint
  escalation_recommended?: boolean
  escalation_reason?: string
  workflow_complete?: boolean
  resolution_summary?: string
}

interface TroubleshootingData extends TroubleshootingState {}

export interface TroubleshootingWorkflowProps {
  troubleshooting: TroubleshootingData
  onStepExecute?: (stepId: string, result: string, feedback?: string) => void
  className?: string
}

export function TroubleshootingWorkflow({ 
  troubleshooting, 
  onStepExecute,
  className = '' 
}: TroubleshootingWorkflowProps) {
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [customerFeedback, setCustomerFeedback] = useState('')
  const [executingStep, setExecutingStep] = useState<string | null>(null)

  const getPhaseIcon = (phase?: string) => {
    switch (phase?.toLowerCase()) {
      case 'initial_assessment':
        return Target
      case 'basic_diagnostics':
        return Activity
      case 'intermediate_diagnostics':
        return ClipboardCheck
      case 'advanced_diagnostics':
        return Zap
      case 'specialized_testing':
        return Shield
      case 'escalation_preparation':
        return AlertTriangle
      case 'resolution_verification':
        return CheckCircle
      default:
        return Activity
    }
  }

  const getPhaseColor = (phase?: string) => {
    switch (phase?.toLowerCase()) {
      case 'initial_assessment':
        return 'bg-blue-100 text-blue-800'
      case 'basic_diagnostics':
        return 'bg-green-100 text-green-800'
      case 'intermediate_diagnostics':
        return 'bg-yellow-100 text-yellow-800'
      case 'advanced_diagnostics':
        return 'bg-orange-100 text-orange-800'
      case 'specialized_testing':
        return 'bg-purple-100 text-purple-800'
      case 'escalation_preparation':
        return 'bg-red-100 text-red-800'
      case 'resolution_verification':
        return 'bg-emerald-100 text-emerald-800'
      default:
        return 'bg-gray-100 text-gray-800'
    }
  }

  const getComplexityColor = (complexity?: string) => {
    switch (complexity?.toLowerCase()) {
      case 'beginner':
        return 'text-green-600'
      case 'intermediate':
        return 'text-yellow-600'
      case 'advanced':
        return 'text-orange-600'
      case 'expert':
        return 'text-red-600'
      default:
        return 'text-gray-600'
    }
  }

  const handleStepResult = (result: 'success' | 'failure' | 'partial' | 'skip') => {
    if (!selectedStepId || !onStepExecute) return
    
    setExecutingStep(selectedStepId)
    onStepExecute(selectedStepId, result, customerFeedback)
    
    // Reset state after execution
    setTimeout(() => {
      setSelectedStepId(null)
      setCustomerFeedback('')
      setExecutingStep(null)
    }, 500)
  }

  const PhaseIcon = getPhaseIcon(troubleshooting.current_phase)

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Session Header */}
      {troubleshooting.session_id && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <PhaseIcon className="h-5 w-5 text-primary" />
                <CardTitle className="text-base">Troubleshooting Session</CardTitle>
              </div>
              {troubleshooting.session_id && (
                <Badge variant="outline" className="text-xs">
                  {troubleshooting.session_id.slice(0, 8)}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Progress Bar */}
            {troubleshooting.progress_percentage !== undefined && (
              <div className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Progress</span>
                  <span className="font-medium">{troubleshooting.progress_percentage.toFixed(0)}%</span>
                </div>
                <Progress value={troubleshooting.progress_percentage} className="h-2" />
              </div>
            )}

            {/* Current Phase */}
            {troubleshooting.current_phase && (
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Current Phase:</span>
                <Badge className={getPhaseColor(troubleshooting.current_phase)} variant="secondary">
                  {troubleshooting.current_phase.replace(/_/g, ' ').toUpperCase()}
                </Badge>
              </div>
            )}

            {/* Verification Status */}
            {troubleshooting.verification_status && (
              <div className="space-y-2">
                {troubleshooting.verification_status.checkpoints_passed && troubleshooting.verification_status.checkpoints_passed.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {troubleshooting.verification_status.checkpoints_passed.map((checkpoint, idx) => (
                      <Badge key={idx} variant="outline" className="text-xs">
                        <CheckCircle className="h-3 w-3 mr-1 text-green-500" />
                        {checkpoint}
                      </Badge>
                    ))}
                  </div>
                )}
                {troubleshooting.verification_status.current_verification && (
                  <p className="text-xs text-muted-foreground">
                    Current verification: {troubleshooting.verification_status.current_verification}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Current Step */}
      {troubleshooting.current_step && (
        <Card className="border-primary/20">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <PlayCircle className="h-4 w-4 text-primary" />
              <CardTitle className="text-sm font-medium">Current Step</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <h4 className="font-medium text-sm">{troubleshooting.current_step.name}</h4>
              <p className="text-sm text-muted-foreground mt-1">
                {troubleshooting.current_step.description}
              </p>
            </div>
            
            {troubleshooting.current_step.expected_outcome && (
              <div className="p-2 bg-muted/50 rounded text-xs">
                <span className="font-medium">Expected outcome:</span> {troubleshooting.current_step.expected_outcome}
              </div>
            )}

            <div className="flex items-center gap-4 text-xs text-muted-foreground">
              {troubleshooting.current_step.time_estimate && (
                <span>⏱️ {troubleshooting.current_step.time_estimate}</span>
              )}
              {troubleshooting.current_step.complexity && (
                <span className={getComplexityColor(troubleshooting.current_step.complexity)}>
                  Level: {troubleshooting.current_step.complexity}
                </span>
              )}
              {troubleshooting.current_step.requires_customer_action && (
                <Badge variant="secondary" className="text-xs">
                  <MessageSquare className="h-3 w-3 mr-1" />
                  Customer Action Required
                </Badge>
              )}
            </div>

            {/* Action Buttons */}
            {onStepExecute && (
              <div className="flex flex-wrap gap-2 pt-2">
                <Button
                  size="sm"
                  variant="default"
                  onClick={() => handleStepResult('success')}
                  disabled={executingStep === troubleshooting.current_step.id}
                >
                  <CheckCircle className="h-3 w-3 mr-1" />
                  Success
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => handleStepResult('failure')}
                  disabled={executingStep === troubleshooting.current_step.id}
                >
                  <XCircle className="h-3 w-3 mr-1" />
                  Failed
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => handleStepResult('partial')}
                  disabled={executingStep === troubleshooting.current_step.id}
                >
                  Partial
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleStepResult('skip')}
                  disabled={executingStep === troubleshooting.current_step.id}
                >
                  <SkipForward className="h-3 w-3 mr-1" />
                  Skip
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Next Steps */}
      {troubleshooting.next_steps && troubleshooting.next_steps.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Next Steps</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {troubleshooting.next_steps.map((step, idx) => (
                <div
                  key={step.id}
                  className={`p-3 rounded-lg border transition-colors cursor-pointer ${
                    selectedStepId === step.id 
                      ? 'border-primary bg-primary/5' 
                      : 'border-border hover:bg-muted/50'
                  }`}
                  onClick={() => setSelectedStepId(selectedStepId === step.id ? null : step.id)}
                >
                  <div className="flex items-start gap-2">
                    <ChevronRight className="h-4 w-4 mt-0.5 text-muted-foreground" />
                    <div className="flex-1">
                      <h5 className="text-sm font-medium">{step.name}</h5>
                      <p className="text-xs text-muted-foreground mt-1">{step.description}</p>
                      
                      {selectedStepId === step.id && (
                        <div className="mt-3 space-y-3">
                          {step.expected_outcome && (
                            <div className="p-2 bg-muted/50 rounded text-xs">
                              <span className="font-medium">Expected:</span> {step.expected_outcome}
                            </div>
                          )}
                          
                          {onStepExecute && (
                            <>
                              <Textarea
                                placeholder="Customer feedback (optional)"
                                value={customerFeedback}
                                onChange={(e) => setCustomerFeedback(e.target.value)}
                                className="text-xs h-16"
                              />
                              
                              <div className="flex gap-2">
                                <Button
                                  size="sm"
                                  variant="default"
                                  onClick={() => {
                                    setExecutingStep(step.id)
                                    onStepExecute(step.id, 'success', customerFeedback)
                                    setSelectedStepId(null)
                                    setCustomerFeedback('')
                                  }}
                                >
                                  Execute Step
                                </Button>
                              </div>
                            </>
                          )}
                        </div>
                      )}
                      
                      <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                        {step.time_estimate && <span>⏱️ {step.time_estimate}</span>}
                        {step.complexity && (
                          <span className={getComplexityColor(step.complexity)}>
                            {step.complexity}
                          </span>
                        )}
                        {step.requires_customer_action && (
                          <MessageSquare className="h-3 w-3" />
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Escalation Alert */}
      {troubleshooting.escalation_recommended && (
        <Alert className="border-orange-200 bg-orange-50">
          <AlertTriangle className="h-4 w-4 text-orange-600" />
          <AlertDescription>
            <strong className="text-orange-900">Escalation Recommended</strong>
            {troubleshooting.escalation_reason && (
              <p className="text-sm text-orange-800 mt-1">{troubleshooting.escalation_reason}</p>
            )}
          </AlertDescription>
        </Alert>
      )}

      {/* Resolution Summary */}
      {troubleshooting.workflow_complete && troubleshooting.resolution_summary && (
        <Card className="border-green-200 bg-green-50">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-600" />
              <CardTitle className="text-base text-green-900">Resolution Achieved</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-green-800">{troubleshooting.resolution_summary}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}