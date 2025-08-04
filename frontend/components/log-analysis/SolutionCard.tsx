"use client"

import React, { useState } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { 
  ChevronDown,
  ChevronUp,
  Clock,
  Target,
  CheckCircle,
  Users,
  Lightbulb
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { 
  type LogSolution, 
  formatTimeEstimate,
  formatSuccessProbability
} from '@/lib/log-analysis-utils'
import { SeverityBadge } from './SeverityBadge'

interface SolutionCardProps {
  solution: LogSolution
  isExpanded?: boolean
  onToggle?: () => void
}

export function SolutionCard({ solution, isExpanded = false, onToggle }: SolutionCardProps) {
  const [isOpen, setIsOpen] = useState(isExpanded)
  
  const handleToggle = () => {
    const newState = !isOpen
    setIsOpen(newState)
    onToggle?.()
  }

  const severity = solution.priority || 'Medium'
  const timeEstimate = formatTimeEstimate(
    solution.estimated_time || 
    solution.estimated_time_minutes || 
    solution.estimated_total_time_minutes ||
    solution.eta_min || 
    "Unknown"
  )
  const successProb = formatSuccessProbability(
    solution.success_probability || 
    solution.success_prob || 
    "Unknown"
  )
  
  const title = solution.title || solution.solution_summary || solution.summary || "Solution"
  const details = solution.details || solution.description || solution.solution_summary || ""
  const steps = solution.implementation_steps || solution.steps || []
  const affectedAccounts = solution.affected_accounts || []

  return (
    <Collapsible open={isOpen} onOpenChange={handleToggle}>
      <Card className={cn(
        "w-full transition-all duration-200",
        "bg-neutral-card border-border",
        isOpen && "ring-1 ring-primary/20"
      )}>
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer hover:bg-muted/20 transition-colors pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <Lightbulb className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <h4 className="text-sm font-semibold text-foreground line-clamp-2">
                    {title}
                  </h4>
                  {details && (
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                      {details}
                    </p>
                  )}
                  
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <SeverityBadge level={severity.toLowerCase() as 'critical' | 'high' | 'medium'} />
                    
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      <span>{timeEstimate}</span>
                    </div>
                    
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Target className="h-3 w-3" />
                      <span>{successProb}</span>
                    </div>
                  </div>
                </div>
              </div>
              
              <Button
                variant="ghost"
                size="sm"
                className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                aria-label={isOpen ? "Collapse solution details" : "Expand solution details"}
                aria-expanded={isOpen}
              >
                {isOpen ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </Button>
            </div>
          </CardHeader>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <CardContent className="pt-0">
            {/* Affected Accounts */}
            {affectedAccounts.length > 0 && (
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <Users className="h-3 w-3 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">
                    Affected Accounts ({affectedAccounts.length})
                  </span>
                </div>
                <div className="flex flex-wrap gap-1">
                  {affectedAccounts.slice(0, 3).map((account, idx) => (
                    <Badge key={idx} variant="outline" className="text-xs">
                      {account}
                    </Badge>
                  ))}
                  {affectedAccounts.length > 3 && (
                    <Badge variant="outline" className="text-xs text-muted-foreground">
                      +{affectedAccounts.length - 3} more
                    </Badge>
                  )}
                </div>
              </div>
            )}

            {/* Implementation Steps */}
            {steps.length > 0 && (
              <div className="mb-4">
                <h5 className="text-xs font-medium text-foreground mb-3 flex items-center gap-2">
                  <CheckCircle className="h-3 w-3" />
                  Implementation Steps ({steps.length})
                </h5>
                <ul className="list-disc list-inside text-sm leading-6 pl-1 space-y-2">
                  {steps.map((step, idx) => {
                    // Handle both string steps and object steps
                    const stepText = typeof step === 'string' 
                      ? step 
                      : step.action || step.description || `Step ${idx + 1}`
                    
                    return (
                      <li key={idx} className="text-muted-foreground">
                        {stepText}
                        {typeof step === 'object' && step.specific_settings && Object.keys(step.specific_settings).length > 0 && (
                          <div className="mt-1 text-xs text-muted-foreground pl-4">
                            <div className="grid grid-cols-2 gap-1">
                              {Object.entries(step.specific_settings).slice(0, 4).map(([key, value]) => (
                                <div key={key} className="text-xs">
                                  <span className="font-medium">{key}:</span> {String(value)}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {typeof step === 'object' && step.expected_outcome && (
                          <div className="mt-1 text-xs text-muted-foreground italic pl-4">
                            Expected: {step.expected_outcome}
                          </div>
                        )}
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}

            {/* Expected Outcome */}
            {solution.expected_outcome && (
              <div className="p-3 bg-muted/30 rounded-lg">
                <div className="text-xs font-medium text-foreground mb-1">Expected Result</div>
                <div className="text-xs text-muted-foreground italic">
                  {solution.expected_outcome}
                </div>
              </div>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}