"use client"

import React, { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'  
import { Separator } from '@/components/ui/separator'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { AgentAvatar } from '@/components/ui/AgentAvatar'
import { MarkdownMessage } from '@/components/markdown/MarkdownMessage'
import {
  MessageCircle,
  FileSearch,
  Search,
  User,
  Bot,
  Copy,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle,
  XCircle,
  Globe,
  BookOpen,
  FileText
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { EnhancedLogAnalysisContainer } from '@/components/log-analysis/EnhancedLogAnalysisContainer'
import { type LogAnalysisData, type EnhancedLogAnalysisData } from '@/lib/log-analysis-utils'
import { ExecutiveSummaryRenderer } from '@/components/markdown/ExecutiveSummaryRenderer'

interface Source {
  id: string
  title: string
  url: string
  snippet?: string
  type: 'web' | 'knowledge_base' | 'documentation'
}

interface MessageMetadata {
  confidence?: number
  sources?: Source[]
  analysisResults?: any
  routingReason?: string
}

interface MessageBubbleProps {
  id: string
  type: "user" | "agent" | "system"
  content: string
  timestamp: Date
  agentType?: "primary" | "log_analyst" | "researcher"
  metadata?: MessageMetadata
  streaming?: boolean
  onRetry?: () => void
  onRate?: (rating: 'up' | 'down') => void
}

function CitationDisplay({ sources }: { sources: Source[] }) {
  const [isExpanded, setIsExpanded] = useState(false)
  
  const getSourceIcon = (type: string) => {
    switch (type) {
      case 'web':
        return <Globe className="w-3 h-3" />
      case 'knowledge_base':
        return <BookOpen className="w-3 h-3" />
      case 'documentation':
        return <FileText className="w-3 h-3" />
      default:
        return <ExternalLink className="w-3 h-3" />
    }
  }
  
  if (!sources || sources.length === 0) return null
  
  return (
    <div className="mt-4 pt-3 border-t border-border/50">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsExpanded(!isExpanded)}
        className="h-auto p-0 font-medium text-xs text-chat-metadata hover:text-foreground mb-2"
      >
        <span className="mr-1">Sources ({sources.length})</span>
        {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </Button>
      
      {isExpanded && (
        <div className="space-y-2">
          {sources.map((source, idx) => (
            <div key={idx} className="citation-hover rounded-lg border border-border/50 p-3 bg-muted/30">
              <div className="flex items-start gap-2">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-primary/10 text-primary text-xs font-medium flex-shrink-0">
                  {idx + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1 mb-1">
                    {getSourceIcon(source.type)}
                    <span className="text-xs font-medium text-foreground truncate">
                      {source.title || 'Source'}
                    </span>
                  </div>
                  <a 
                    href={source.url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-xs text-primary hover:underline break-all"
                  >
                    {source.url}
                  </a>
                  {source.snippet && (
                    <p className="text-xs text-chat-metadata mt-1 line-clamp-2">
                      {source.snippet}
                    </p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-auto p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => window.open(source.url, '_blank')}
                >
                  <ExternalLink className="w-3 h-3" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AnalysisResults({ results }: { results: any }) {
  const [isExpanded, setIsExpanded] = useState(true) // Start expanded for log analysis
  
  const getSeverityIcon = (severity: string) => {
    switch (severity?.toLowerCase()) {
      case 'high':
      case 'critical':
        return <XCircle className="w-4 h-4 text-red-500" />
      case 'medium':
        return <AlertCircle className="w-4 h-4 text-yellow-500" />
      case 'low':
        return <CheckCircle className="w-4 h-4 text-green-500" />
      default:
        return null
    }
  }
  
  const getHealthStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'critical':
        return 'text-red-500 bg-red-500/10'
      case 'degraded':
        return 'text-yellow-500 bg-yellow-500/10'
      case 'healthy':
        return 'text-green-500 bg-green-500/10'
      default:
        return 'text-gray-500 bg-gray-500/10'
    }
  }
  
  return (
    <div className="mt-4 pt-3 border-t border-border/50">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsExpanded(!isExpanded)}
        className="h-auto p-0 font-medium text-xs text-chat-metadata hover:text-foreground mb-3"
      >
        <span className="mr-1">Log Analysis Results</span>
        {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </Button>
      
      {/* System Health Overview */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="bg-muted/30 rounded-lg p-2">
          <div className="text-xs font-medium text-foreground">System Health</div>
          <div className={cn("text-xs font-semibold px-2 py-1 rounded", getHealthStatusColor(results.health_status))}>
            {results.health_status || 'Unknown'}
          </div>
        </div>
        <div className="bg-muted/30 rounded-lg p-2">
          <div className="text-xs font-medium text-foreground">Mailbird Version</div>
          <div className="text-xs text-chat-metadata">
            {results.system_metadata?.mailbird_version || 'Unknown'}
          </div>
        </div>
      </div>
      
      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-2 mb-3">
        <div className="text-center">
          <div className="text-xs font-medium text-foreground">{results.system_metadata?.account_count || 0}</div>
          <div className="text-xs text-chat-metadata">Accounts</div>
        </div>
        <div className="text-center">
          <div className="text-xs font-medium text-foreground">{results.system_metadata?.folder_count || 0}</div>
          <div className="text-xs text-chat-metadata">Folders</div>
        </div>
        <div className="text-center">
          <div className="text-xs font-medium text-foreground">{results.system_metadata?.database_size_mb || 0} MB</div>
          <div className="text-xs text-chat-metadata">DB Size</div>
        </div>
        <div className="text-center">
          <div className="text-xs font-medium text-foreground">{results.identified_issues?.length || 0}</div>
          <div className="text-xs text-chat-metadata">Issues</div>
        </div>
      </div>
      
      {isExpanded && (
        <div className="space-y-4">
          {/* Account Analysis Section */}
          {results.account_analysis?.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-foreground">Account-Specific Analysis:</div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border/50">
                      <th className="text-left py-1 px-2">Account</th>
                      <th className="text-left py-1 px-2">Status</th>
                      <th className="text-left py-1 px-2">Issues</th>
                      <th className="text-left py-1 px-2">Primary Problems</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.account_analysis.slice(0, 5).map((account: any, idx: number) => (
                      <tr key={idx} className="border-b border-border/20">
                        <td className="py-1 px-2 font-medium">{account.account}</td>
                        <td className="py-1 px-2">
                          <Badge variant="outline" className={cn(
                            "text-xs",
                            account.status === 'stable' ? 'text-green-600' :
                            account.status === 'minor issues' ? 'text-yellow-600' :
                            account.status === 'intermittent issues' ? 'text-orange-600' : 'text-red-600'
                          )}>
                            {account.status}
                          </Badge>
                        </td>
                        <td className="py-1 px-2">{account.total_issues}</td>
                        <td className="py-1 px-2">
                          {account.primary_issues?.map(([issue, count]: [string, number]) => (
                            <span key={issue} className="text-chat-metadata">
                              {issue.replace('_', ' ')} ({count})
                            </span>
                          )).slice(0, 2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          
          {/* Issues Section */}
          {results.identified_issues?.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-foreground">Detailed Issues Found:</div>
              {results.identified_issues.map((issue: any, idx: number) => (
                <div key={idx} className="bg-muted/30 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-2">
                    {getSeverityIcon(issue.severity)}
                    <Badge variant="outline" className="text-xs">
                      {issue.severity}
                    </Badge>
                    <span className="text-xs font-medium text-foreground">
                      {issue.category?.replace('_', ' ').toUpperCase()}
                    </span>
                    {issue.occurrences && (
                      <span className="text-xs text-chat-metadata">
                        ({issue.occurrences} times)
                      </span>
                    )}
                  </div>
                  {issue.affected_accounts?.length > 0 && (
                    <div className="text-xs text-chat-metadata mb-1">
                      <strong>Affected Accounts:</strong> {issue.affected_accounts.slice(0, 3).join(', ')}
                      {issue.affected_accounts.length > 3 && ` (+${issue.affected_accounts.length - 3} more)`}
                    </div>
                  )}
                  <div className="text-xs text-chat-metadata mb-1">
                    <strong>Impact:</strong> {issue.user_impact}
                  </div>
                  <div className="text-xs text-chat-metadata">
                    <strong>Root Cause:</strong> {issue.root_cause}
                  </div>
                  {issue.frequency_pattern && (
                    <div className="text-xs text-chat-metadata mt-1">
                      <strong>Pattern:</strong> {issue.frequency_pattern}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          
          {/* Solutions Section */}
          {results.proposed_solutions?.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-foreground">Priority-Based Solutions:</div>
              {results.proposed_solutions.slice(0, 3).map((solution: any, idx: number) => (
                <div key={idx} className={cn(
                  "rounded-lg p-3 border",
                  solution.priority === 'Critical' ? 'bg-red-500/10 border-red-500/20' :
                  solution.priority === 'High' ? 'bg-orange-500/10 border-orange-500/20' :
                  solution.priority === 'Medium' ? 'bg-yellow-500/10 border-yellow-500/20' :
                  'bg-primary/5 border-primary/20'
                )}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={cn(
                        "text-xs",
                        solution.priority === 'Critical' ? 'text-red-600' :
                        solution.priority === 'High' ? 'text-orange-600' :
                        solution.priority === 'Medium' ? 'text-yellow-600' : 'text-blue-600'
                      )}>
                        {solution.priority}
                      </Badge>
                      <Badge variant="outline" className="text-xs text-muted-foreground">
                        {solution.implementation_timeline || 'Day 1'}
                      </Badge>
                    </div>
                    <Badge variant="outline" className={cn(
                      "text-xs",
                      solution.success_probability === 'High' ? 'text-green-600' :
                      solution.success_probability === 'Medium' ? 'text-yellow-600' : 'text-red-600'
                    )}>
                      {solution.success_probability} Success
                    </Badge>
                  </div>
                  
                  <div className="text-xs font-medium text-foreground mb-2">
                    {solution.solution_summary}
                  </div>
                  
                  {solution.affected_accounts?.length > 0 && (
                    <div className="text-xs text-chat-metadata mb-2">
                      <strong>Accounts:</strong> {solution.affected_accounts.slice(0, 2).join(', ')}
                      {solution.affected_accounts.length > 2 && ` (+${solution.affected_accounts.length - 2} more)`}
                    </div>
                  )}
                  
                  <div className="text-xs text-chat-metadata mb-2">
                    <strong>Est. Time:</strong> {solution.estimated_total_time_minutes || solution.estimated_time_minutes || 15} minutes
                  </div>
                  
                  {solution.solution_steps?.length > 0 && (
                    <div className="mt-2">
                      <div className="text-xs font-medium text-foreground mb-1">Key Steps:</div>
                      {solution.solution_steps.slice(0, 3).map((step: any, stepIdx: number) => (
                        <div key={stepIdx} className="text-xs text-chat-metadata pl-2 border-l-2 border-primary/20 mb-1">
                          <span className="font-medium">{step.step_number}.</span> {step.description}
                          {step.specific_settings && (
                            <div className="text-xs text-muted-foreground mt-1 pl-3">
                              {Object.entries(step.specific_settings).map(([key, value]) => (
                                <div key={key}><strong>{key}:</strong> {value as string}</div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                      {solution.solution_steps.length > 3 && (
                        <div className="text-xs text-chat-metadata pl-2">
                          +{solution.solution_steps.length - 3} additional steps
                        </div>
                      )}
                    </div>
                  )}
                  
                  {solution.expected_outcome && (
                    <div className="text-xs text-muted-foreground mt-2 italic">
                      <strong>Expected Result:</strong> {solution.expected_outcome}
                    </div>
                  )}
                </div>
              ))}
              {results.proposed_solutions.length > 3 && (
                <div className="text-xs text-chat-metadata">
                  +{results.proposed_solutions.length - 3} additional solutions available
                </div>
              )}
            </div>
          )}
          
          {/* Immediate Actions */}
          {results.immediate_actions?.length > 0 && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
              <div className="text-xs font-medium text-red-400 mb-2">Immediate Actions Required:</div>
              {results.immediate_actions.map((action: string, idx: number) => (
                <div key={idx} className="text-xs text-red-300 flex items-center gap-2">
                  <AlertCircle className="w-3 h-3" />
                  {action}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TypewriterText({ text, isStreaming }: { text: string, isStreaming: boolean }) {
  const [displayText, setDisplayText] = useState('')
  const [currentIndex, setCurrentIndex] = useState(0)
  
  useEffect(() => {
    if (!isStreaming) {
      setDisplayText(text)
      return
    }
    
    if (currentIndex < text.length) {
      const timer = setTimeout(() => {
        setDisplayText(text.slice(0, currentIndex + 1))
        setCurrentIndex(currentIndex + 1)
      }, 20) // Adjust speed here
      
      return () => clearTimeout(timer)
    }
  }, [text, isStreaming, currentIndex])
  
  return (
    <div className="text-sm leading-relaxed">
      {displayText}
      {isStreaming && currentIndex < text.length && (
        <span className="inline-block w-0.5 h-4 bg-current ml-0.5 animate-pulse" />
      )}
    </div>
  )
}

/**
 * Renders a chat message bubble with support for user, agent, and system messages, including streaming animation, markdown rendering, citations, log analysis results, and interactive actions.
 *
 * Displays avatars, message content, citations, analysis results, and message metadata. Provides copy, rate, and retry actions for agent and system messages. Handles specialized rendering for log analyst messages and legacy analysis formats. Filters out certain system status messages from display.
 *
 * @returns The rendered chat message bubble, or `null` for filtered system messages.
 */
export default function MessageBubble({ 
  id, 
  type, 
  content, 
  timestamp, 
  agentType, 
  metadata, 
  streaming = false,
  onRetry,
  onRate 
}: MessageBubbleProps) {
  const [isHovered, setIsHovered] = useState(false)
  const messageRef = useRef<HTMLDivElement>(null)
  
  const isUser = type === "user"
  const isSystem = type === "system"
  const isAgent = type === "agent"
  
  // Filter out routing system messages and log analysis status messages - these are handled by status components now
  if (isSystem && (
    content.includes("Routing to") || 
    content.includes("Analyzing your request") ||
    content.includes("Processing query") ||
    content.includes("🔍 Analyzing log file") ||
    content.includes("📁 Processing")
  )) {
    return null
  }
  
  const getAgentInfo = () => {
    switch (agentType) {
      case 'primary':
        return { icon: MessageCircle, label: 'Primary Support', color: 'text-blue-400' }
      case 'log_analyst':
        return { icon: FileSearch, label: 'Log Analysis', color: 'text-orange-400' }
      case 'researcher':
        return { icon: Search, label: 'Research', color: 'text-purple-400' }
      default:
        return { icon: Bot, label: 'Assistant', color: 'text-green-400' }
    }
  }
  
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      toast.success('Copied to clipboard')
    } catch (error) {
      toast.error('Failed to copy')
    }
  }
  
  const handleRate = (rating: 'up' | 'down') => {
    if (onRate) {
      onRate(rating)
      toast.success(`Feedback recorded: ${rating === 'up' ? 'Helpful' : 'Not helpful'}`)
    }
  }
  
  const { icon: AgentIcon, label: agentLabel, color: agentColor } = getAgentInfo()
  
  return (
    <div 
      ref={messageRef}
      className={cn(
        "group message-enter mb-6 max-w-none",
        isUser ? "flex justify-end" : "flex justify-start"
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      role={isSystem ? "status" : "article"}
      aria-label={`${isUser ? 'Your message' : `${agentLabel} response`} sent at ${timestamp.toLocaleTimeString()}`}
    >
      <div className={cn(
        "flex items-start gap-3 max-w-4xl w-full mx-auto",
        isUser ? "flex-row-reverse justify-start" : "flex-row"
      )}>
        {/* Avatar */}
        {isUser ? (
          <Avatar className="w-8 h-8 bg-accent/20 border border-accent/30">
            <AvatarFallback className="bg-accent/10 text-accent font-semibold text-sm">
              U
            </AvatarFallback>
          </Avatar>
        ) : (
          <AgentAvatar className="w-8 h-8" />
        )}
        
        {/* Message Content Container */}
        <div className={cn(
          "rounded-xl px-4 py-3 shadow-sm border text-sm leading-relaxed",
          isUser
            ? "bg-accent/10 border-accent/30 text-foreground max-w-[75%] w-fit ml-auto"
            : isSystem
            ? "bg-muted/50 text-muted-foreground border-border/50 flex-1"
            : "bg-muted/70 dark:bg-zinc-800 border-border/40 text-foreground flex-1"
        )}>
          
          {/* Message Text */}
          {streaming ? (
            <TypewriterText text={content} isStreaming={streaming} />
          ) : (
            // For log analysis, render structured components instead of raw text
            agentType === 'log_analyst' && metadata?.analysisResults ? null : (
              // Use markdown rendering for all assistant responses
              !isUser ? (
                <MarkdownMessage content={content} />
              ) : (
                <div className="text-sm leading-relaxed whitespace-pre-wrap">
                  {content}
                </div>
              )
            )
          )}
          
          {/* Enhanced Log Analysis Container */}
          {agentType === 'log_analyst' && metadata?.analysisResults && !streaming && (
            <EnhancedLogAnalysisContainer 
              data={metadata.analysisResults as (EnhancedLogAnalysisData | LogAnalysisData)}
              className="mt-4 w-full"
            />
          )}
          
          {/* Legacy Analysis Results (fallback for old format) */}
          {metadata?.analysisResults && agentType !== 'log_analyst' && (
            <AnalysisResults results={metadata.analysisResults} />
          )}
          
          {/* Enhanced Executive Summary with timeline/priority block removal */}
          {agentType === 'log_analyst' && content.includes('##') && !metadata?.analysisResults && !streaming && (
            <div className="mt-4 pt-3 border-t border-border/50">
              <ExecutiveSummaryRenderer 
                content={content}
                className="bg-transparent border-0 shadow-none"
              />
            </div>
          )}
          
          {/* Citations */}
          {metadata?.sources && metadata.sources.length > 0 && (
            <CitationDisplay sources={metadata.sources} />
          )}
          
          {/* Message Footer */}
          <div className="flex items-center justify-between mt-3 pt-2">
            <div className="flex items-center gap-2 text-xs text-chat-metadata">
              {!isUser && (
                <span>{timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              )}
              {metadata?.routingReason && (
                <span className="opacity-70">• {metadata.routingReason}</span>
              )}
            </div>
            
            {/* Action Buttons */}
            {!isUser && (isHovered || streaming) && (
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopy}
                  className="h-6 w-6 p-0 text-chat-metadata hover:text-foreground"
                >
                  <Copy className="w-3 h-3" />
                </Button>
                
                {onRate && !streaming && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRate('up')}
                      className="h-6 w-6 p-0 text-chat-metadata hover:text-green-500"
                    >
                      <ThumbsUp className="w-3 h-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRate('down')}
                      className="h-6 w-6 p-0 text-chat-metadata hover:text-red-500"
                    >
                      <ThumbsDown className="w-3 h-3" />
                    </Button>
                  </>
                )}
                
                {onRetry && !streaming && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onRetry}
                    className="h-6 w-6 p-0 text-chat-metadata hover:text-primary"
                  >
                    <RotateCcw className="w-3 h-3" />
                  </Button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}