"use client"

import React, { useState } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { 
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Users,
  Activity,
  Target,
  Clock
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  type LogIssue,
  type LogSolution,
  severityClasses
} from '@/lib/log-analysis-utils'
import { SeverityBadge } from './SeverityBadge'

interface IssueCardProps {
  issue: LogIssue
  solutions?: LogSolution[]
  isExpanded?: boolean
  onToggle?: () => void
}

export function IssueCard({ issue, solutions, isExpanded = false, onToggle }: IssueCardProps) {
  const [isOpen, setIsOpen] = useState(isExpanded)
  
  const handleToggle = () => {
    const newState = !isOpen
    setIsOpen(newState)
    onToggle?.()
  }

  const severity = issue.severity || 'Medium'
  const affectedAccounts = issue.affected_accounts || []
  const occurrences = issue.occurrences || 0
  
  // Enhanced field mapping for backend compatibility
  const title = issue.title || issue.signature || issue.description || `${issue.category} Issue`
  const description = issue.description || issue.signature || ''
  const impact = issue.impact || issue.user_impact || issue.business_impact
  const rootCause = issue.root_cause
  const pattern = issue.frequency_pattern

  return (
    <Collapsible open={isOpen} onOpenChange={handleToggle}>
      <Card className={cn(
        "w-full transition-all duration-200",
        "bg-card border-border text-card-foreground",
        isOpen && "ring-1 ring-primary/20"
      )}>
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer hover:bg-muted/20 transition-colors pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <AlertTriangle className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <SeverityBadge level={severity.toLowerCase() as 'critical' | 'high' | 'medium'} />
                    
                    <Badge variant="outline" className="text-xs text-muted-foreground">
                      {issue.category?.replace('_', ' ').toUpperCase()}
                    </Badge>

                    {occurrences > 0 && (
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Activity className="h-3 w-3" />
                        <span>{occurrences} times</span>
                      </div>
                    )}
                  </div>
                  
                  <h4 className="text-sm font-semibold text-foreground mb-1 line-clamp-2">
                    {title}
                  </h4>
                  
                  {affectedAccounts.length > 0 && (
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Users className="h-3 w-3" />
                      <span>
                        {affectedAccounts.slice(0, 2).join(', ')}
                        {affectedAccounts.length > 2 && ` (+${affectedAccounts.length - 2} more)`}
                      </span>
                    </div>
                  )}
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
                  aria-label={isOpen ? "Collapse issue details" : "Expand issue details"}
                  aria-expanded={isOpen}
                >
                  {isOpen ? (
                    <ChevronUp className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
          </CardHeader>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <CardContent className="pt-0 space-y-4">
            {/* Issue Details */}
            <div className="grid gap-4">
              {description && description !== title && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="h-3 w-3 text-muted-foreground" />
                    <span className="text-xs font-medium text-foreground">Description</span>
                  </div>
                  <p className="text-xs text-muted-foreground pl-5">{description}</p>
                </div>
              )}

              {impact && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Target className="h-3 w-3 text-muted-foreground" />
                    <span className="text-xs font-medium text-foreground">Impact</span>
                  </div>
                  <p className="text-xs text-muted-foreground pl-5">{impact}</p>
                </div>
              )}

              {rootCause && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="h-3 w-3 text-muted-foreground" />
                    <span className="text-xs font-medium text-foreground">Root Cause</span>
                  </div>
                  <p className="text-xs text-muted-foreground pl-5">{rootCause}</p>
                </div>
              )}

              {pattern && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Clock className="h-3 w-3 text-muted-foreground" />
                    <span className="text-xs font-medium text-foreground">Pattern</span>
                  </div>
                  <p className="text-xs text-muted-foreground pl-5">{pattern}</p>
                </div>
              )}

              {affectedAccounts.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Users className="h-3 w-3 text-muted-foreground" />
                    <span className="text-xs font-medium text-foreground">
                      Affected Accounts ({affectedAccounts.length})
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1 pl-5">
                    {affectedAccounts.map((account, idx) => (
                      <Badge key={idx} variant="outline" className="text-xs">
                        {account}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}