/**
 * ValidationPanel Component
 * 
 * Real-time content validation with AI quality metrics display,
 * platform detection results, and processing recommendations.
 * 
 * Part of FeedMe v2.0 Phase 3C: Smart Conversation Editor
 */

'use client'

import React, { useState, useCallback, useMemo, useEffect } from 'react'
import { 
  Shield, CheckCircle2, AlertTriangle, XCircle, Zap, 
  Activity, Target, TrendingUp, AlertCircle, Info,
  RefreshCw, Settings, ChevronDown, ChevronRight,
  FileText, MessageSquare, Bot, User, Clock,
  BarChart3, PieChart, LineChart
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'

// Types
interface ValidationPanelProps {
  content: string
  segments?: ConversationSegment[]
  qaPairs?: QAPair[]
  onValidationComplete?: (results: ValidationResults) => void
  onRecommendationApply?: (recommendation: ProcessingRecommendation) => void
  enableRealTimeValidation?: boolean
  enablePlatformDetection?: boolean
  className?: string
}

interface ConversationSegment {
  id: string
  type: 'customer' | 'agent' | 'system' | 'metadata'
  content: string
  confidence: number
  validationStatus: 'valid' | 'warning' | 'error'
  validationMessage?: string
}

interface QAPair {
  id: string
  question: string
  answer: string
  confidence: number
  quality_score: number
  validation_status: 'valid' | 'needs_review' | 'invalid'
}

interface ValidationResults {
  overallScore: number
  contentQuality: ContentQuality
  platformDetection: PlatformDetection
  processingRecommendations: ProcessingRecommendation[]
  qualityMetrics: QualityMetrics
  issueAnalysis: IssueAnalysis
  performanceMetrics: PerformanceMetrics
  validatedAt: string
}

interface ContentQuality {
  score: number
  factors: QualityFactor[]
  improvements: string[]
  strengths: string[]
}

interface QualityFactor {
  name: string
  score: number
  weight: number
  description: string
  status: 'excellent' | 'good' | 'needs_improvement' | 'poor'
}

interface PlatformDetection {
  platform: 'zendesk' | 'intercom' | 'freshdesk' | 'helpscout' | 'custom' | 'unknown'
  confidence: number
  indicators: string[]
  formatCompliance: number
  extractabilityScore: number
}

interface ProcessingRecommendation {
  id: string
  type: 'extraction' | 'segmentation' | 'quality' | 'optimization'
  priority: 'high' | 'medium' | 'low'
  title: string
  description: string
  impact: string
  effort: 'low' | 'medium' | 'high'
  actionable: boolean
  automatable: boolean
}

interface QualityMetrics {
  completeness: number
  clarity: number
  consistency: number
  accuracy: number
  relevance: number
  usability: number
}

interface IssueAnalysis {
  criticalIssues: ValidationIssue[]
  warnings: ValidationIssue[]
  suggestions: ValidationIssue[]
  totalIssues: number
}

interface ValidationIssue {
  id: string
  type: 'format' | 'content' | 'structure' | 'quality' | 'compliance'
  severity: 'critical' | 'warning' | 'suggestion'
  title: string
  description: string
  location?: string
  fix?: string
  autoFixable: boolean
}

interface PerformanceMetrics {
  processingTime: number
  extractionEfficiency: number
  expectedQuality: number
  resourceUsage: number
  optimizationPotential: number
}

// Quality Factor Component
const QualityFactorCard: React.FC<{
  factor: QualityFactor
  showDetails?: boolean
}> = ({ factor, showDetails = false }) => {
  const getStatusColor = (status: QualityFactor['status']) => {
    switch (status) {
      case 'excellent': return 'text-green-600 bg-green-100'
      case 'good': return 'text-blue-600 bg-blue-100'
      case 'needs_improvement': return 'text-yellow-600 bg-yellow-100'
      case 'poor': return 'text-red-600 bg-red-100'
    }
  }

  const getStatusIcon = (status: QualityFactor['status']) => {
    switch (status) {
      case 'excellent': return <CheckCircle2 className="h-3 w-3" />
      case 'good': return <CheckCircle2 className="h-3 w-3" />
      case 'needs_improvement': return <AlertTriangle className="h-3 w-3" />
      case 'poor': return <XCircle className="h-3 w-3" />
    }
  }

  return (
    <div className="p-3 border rounded-lg">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{factor.name}</span>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <div className={cn('flex items-center gap-1 px-2 py-1 rounded-full text-xs', getStatusColor(factor.status))}>
                  {getStatusIcon(factor.status)}
                  {factor.status.replace('_', ' ')}
                </div>
              </TooltipTrigger>
              <TooltipContent>
                <p>{factor.description}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Weight: {factor.weight}%</span>
          <Badge variant="outline" className="text-xs">
            {Math.round(factor.score * 100)}%
          </Badge>
        </div>
      </div>
      
      <Progress value={factor.score * 100} className="h-2" />
      
      {showDetails && (
        <p className="text-xs text-muted-foreground mt-2">{factor.description}</p>
      )}
    </div>
  )
}

// Platform Detection Card
const PlatformDetectionCard: React.FC<{
  detection: PlatformDetection
  isExpanded: boolean
  onToggle: () => void
}> = ({ detection, isExpanded, onToggle }) => {
  const getPlatformIcon = (platform: string) => {
    // In a real app, these would be actual platform icons
    switch (platform) {
      case 'zendesk': return '🎫'
      case 'intercom': return '💬'
      case 'freshdesk': return '🎧'
      case 'helpscout': return '🚁'
      case 'custom': return '⚙️'
      default: return '❓'
    }
  }

  const getPlatformName = (platform: string) => {
    return platform.charAt(0).toUpperCase() + platform.slice(1)
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <Collapsible open={isExpanded} onOpenChange={onToggle}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between p-0">
              <CardTitle className="text-sm flex items-center gap-2">
                <Shield className="h-4 w-4" />
                Platform Detection
              </CardTitle>
              {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
          </CollapsibleTrigger>
          
          <CollapsibleContent className="space-y-3 pt-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-lg">{getPlatformIcon(detection.platform)}</span>
                <span className="font-medium">{getPlatformName(detection.platform)}</span>
              </div>
              <Badge variant="outline" className="text-xs">
                {Math.round(detection.confidence * 100)}% confidence
              </Badge>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Format Compliance</span>
                <span className="font-medium">{Math.round(detection.formatCompliance * 100)}%</span>
              </div>
              <Progress value={detection.formatCompliance * 100} className="h-2" />
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Extractability</span>
                <span className="font-medium">{Math.round(detection.extractabilityScore * 100)}%</span>
              </div>
              <Progress value={detection.extractabilityScore * 100} className="h-2" />
            </div>

            {detection.indicators.length > 0 && (
              <div>
                <span className="text-xs text-muted-foreground mb-1 block">Detection Indicators:</span>
                <div className="flex gap-1 flex-wrap">
                  {detection.indicators.map((indicator, index) => (
                    <Badge key={index} variant="secondary" className="text-xs">
                      {indicator}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>
      </CardHeader>
    </Card>
  )
}

// Issues List Component
const IssuesListCard: React.FC<{
  analysis: IssueAnalysis
  onFixIssue: (issueId: string) => void
  isExpanded: boolean
  onToggle: () => void
}> = ({ analysis, onFixIssue, isExpanded, onToggle }) => {
  const getIssueIcon = (severity: ValidationIssue['severity']) => {
    switch (severity) {
      case 'critical': return <XCircle className="h-4 w-4 text-red-500" />
      case 'warning': return <AlertTriangle className="h-4 w-4 text-yellow-500" />
      case 'suggestion': return <Info className="h-4 w-4 text-blue-500" />
    }
  }

  const allIssues = [
    ...analysis.criticalIssues,
    ...analysis.warnings,
    ...analysis.suggestions
  ]

  return (
    <Card>
      <CardHeader className="pb-3">
        <Collapsible open={isExpanded} onOpenChange={onToggle}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between p-0">
              <CardTitle className="text-sm flex items-center gap-2">
                <AlertCircle className="h-4 w-4" />
                Issues & Suggestions ({analysis.totalIssues})
              </CardTitle>
              {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
          </CollapsibleTrigger>
          
          <CollapsibleContent className="space-y-3 pt-3">
            {allIssues.length > 0 ? (
              <ScrollArea className="max-h-60">
                <div className="space-y-2">
                  {allIssues.map(issue => (
                    <div key={issue.id} className="p-2 border rounded">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2 min-w-0 flex-1">
                          {getIssueIcon(issue.severity)}
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium">{issue.title}</div>
                            <div className="text-xs text-muted-foreground">{issue.description}</div>
                            {issue.location && (
                              <div className="text-xs text-muted-foreground mt-1">
                                Location: {issue.location}
                              </div>
                            )}
                          </div>
                        </div>
                        
                        {issue.autoFixable && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onFixIssue(issue.id)}
                            className="h-6 px-2 text-xs"
                          >
                            Fix
                          </Button>
                        )}
                      </div>
                      
                      {issue.fix && (
                        <div className="mt-2 p-2 bg-muted rounded text-xs">
                          <strong>Suggested fix:</strong> {issue.fix}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            ) : (
              <div className="text-center py-4">
                <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-green-500" />
                <p className="text-sm text-muted-foreground">No issues found</p>
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>
      </CardHeader>
    </Card>
  )
}

// Quality Metrics Chart
const QualityMetricsChart: React.FC<{
  metrics: QualityMetrics
  isExpanded: boolean
  onToggle: () => void
}> = ({ metrics, isExpanded, onToggle }) => {
  const metricData = [
    { name: 'Completeness', value: metrics.completeness, icon: CheckCircle2 },
    { name: 'Clarity', value: metrics.clarity, icon: Eye },
    { name: 'Consistency', value: metrics.consistency, icon: Target },
    { name: 'Accuracy', value: metrics.accuracy, icon: Shield },
    { name: 'Relevance', value: metrics.relevance, icon: TrendingUp },
    { name: 'Usability', value: metrics.usability, icon: User }
  ]

  return (
    <Card>
      <CardHeader className="pb-3">
        <Collapsible open={isExpanded} onOpenChange={onToggle}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between p-0">
              <CardTitle className="text-sm flex items-center gap-2">
                <BarChart3 className="h-4 w-4" />
                Quality Metrics
              </CardTitle>
              {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
          </CollapsibleTrigger>
          
          <CollapsibleContent className="space-y-3 pt-3">
            <div className="space-y-3">
              {metricData.map(metric => {
                const IconComponent = metric.icon
                return (
                  <div key={metric.name} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <IconComponent className="h-3 w-3 text-muted-foreground" />
                        <span>{metric.name}</span>
                      </div>
                      <span className="font-medium">{Math.round(metric.value * 100)}%</span>
                    </div>
                    <Progress value={metric.value * 100} className="h-2" />
                  </div>
                )
              })}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </CardHeader>
    </Card>
  )
}

// Processing Recommendations
const ProcessingRecommendationsCard: React.FC<{
  recommendations: ProcessingRecommendation[]
  onApply: (recommendation: ProcessingRecommendation) => void
  isExpanded: boolean
  onToggle: () => void
}> = ({ recommendations, onApply, isExpanded, onToggle }) => {
  const getPriorityColor = (priority: ProcessingRecommendation['priority']) => {
    switch (priority) {
      case 'high': return 'text-red-600 bg-red-100'
      case 'medium': return 'text-yellow-600 bg-yellow-100'
      case 'low': return 'text-green-600 bg-green-100'
    }
  }

  const getEffortColor = (effort: ProcessingRecommendation['effort']) => {
    switch (effort) {
      case 'low': return 'text-green-600'
      case 'medium': return 'text-yellow-600'
      case 'high': return 'text-red-600'
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <Collapsible open={isExpanded} onOpenChange={onToggle}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" className="w-full justify-between p-0">
              <CardTitle className="text-sm flex items-center gap-2">
                <Zap className="h-4 w-4" />
                Processing Recommendations ({recommendations.length})
              </CardTitle>
              {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
          </CollapsibleTrigger>
          
          <CollapsibleContent className="space-y-3 pt-3">
            {recommendations.length > 0 ? (
              <ScrollArea className="max-h-60">
                <div className="space-y-3">
                  {recommendations.map(recommendation => (
                    <div key={recommendation.id} className="p-3 border rounded">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="flex items-center gap-2">
                          <Badge className={cn('text-xs', getPriorityColor(recommendation.priority))}>
                            {recommendation.priority}
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            {recommendation.type}
                          </Badge>
                          {recommendation.automatable && (
                            <Badge variant="secondary" className="text-xs">
                              Auto
                            </Badge>
                          )}
                        </div>
                        
                        {recommendation.actionable && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onApply(recommendation)}
                            className="h-6 px-2 text-xs"
                          >
                            Apply
                          </Button>
                        )}
                      </div>
                      
                      <h4 className="font-medium text-sm mb-1">{recommendation.title}</h4>
                      <p className="text-xs text-muted-foreground mb-2">{recommendation.description}</p>
                      
                      <div className="flex items-center justify-between text-xs">
                        <span>
                          <strong>Impact:</strong> {recommendation.impact}
                        </span>
                        <span className={getEffortColor(recommendation.effort)}>
                          <strong>Effort:</strong> {recommendation.effort}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            ) : (
              <div className="text-center py-4">
                <Zap className="h-8 w-8 mx-auto mb-2 text-muted-foreground opacity-50" />
                <p className="text-sm text-muted-foreground">No recommendations available</p>
              </div>
            )}
          </CollapsibleContent>
        </Collapsible>
      </CardHeader>
    </Card>
  )
}

// Main Component
export const ValidationPanel: React.FC<ValidationPanelProps> = ({
  content,
  segments = [],
  qaPairs = [],
  onValidationComplete,
  onRecommendationApply,
  enableRealTimeValidation = true,
  enablePlatformDetection = true,
  className
}) => {
  const [validationResults, setValidationResults] = useState<ValidationResults | null>(null)
  const [isValidating, setIsValidating] = useState(false)
  const [validationProgress, setValidationProgress] = useState(0)
  const [autoValidation, setAutoValidation] = useState(enableRealTimeValidation)
  const [expandedSections, setExpandedSections] = useState({
    platform: true,
    quality: true,
    metrics: false,
    issues: true,
    recommendations: true,
    performance: false
  })

  // Mock validation function
  const performValidation = useCallback(async () => {
    setIsValidating(true)
    setValidationProgress(0)

    try {
      const steps = [
        'Analyzing content structure...',
        'Detecting platform format...',
        'Evaluating quality metrics...',
        'Identifying issues...',
        'Generating recommendations...',
        'Finalizing validation...'
      ]

      for (let i = 0; i < steps.length; i++) {
        setValidationProgress((i / steps.length) * 100)
        await new Promise(resolve => setTimeout(resolve, 300))
      }

      // Mock validation results
      const mockResults: ValidationResults = {
        overallScore: 0.82,
        contentQuality: {
          score: 0.78,
          factors: [
            {
              name: 'Structure',
              score: 0.85,
              weight: 20,
              description: 'Clear conversation structure with proper formatting',
              status: 'good'
            },
            {
              name: 'Completeness',
              score: 0.72,
              weight: 25,
              description: 'Most conversation parts are present',
              status: 'needs_improvement'
            },
            {
              name: 'Clarity',
              score: 0.88,
              weight: 20,
              description: 'Messages are clear and understandable',
              status: 'excellent'
            },
            {
              name: 'Extractability',
              score: 0.75,
              weight: 35,
              description: 'Q&A pairs can be extracted with good confidence',
              status: 'good'
            }
          ],
          improvements: [
            'Add missing timestamps for better context',
            'Clarify some ambiguous agent responses',
            'Include customer satisfaction indicators'
          ],
          strengths: [
            'Clear conversation flow',
            'Good question-answer structure',
            'Consistent formatting'
          ]
        },
        platformDetection: {
          platform: 'zendesk',
          confidence: 0.92,
          indicators: ['Ticket format', 'Agent signatures', 'Zendesk headers'],
          formatCompliance: 0.88,
          extractabilityScore: 0.85
        },
        processingRecommendations: [
          {
            id: 'rec-1',
            type: 'extraction',
            priority: 'high',
            title: 'Optimize Q&A extraction',
            description: 'Improve extraction algorithms for better question-answer pair identification',
            impact: 'Increase extraction accuracy by 15%',
            effort: 'medium',
            actionable: true,
            automatable: true
          },
          {
            id: 'rec-2',
            type: 'quality',
            priority: 'medium',
            title: 'Enhance content preprocessing',
            description: 'Add preprocessing steps to clean and normalize conversation content',
            impact: 'Better overall quality scores',
            effort: 'low',
            actionable: true,
            automatable: true
          }
        ],
        qualityMetrics: {
          completeness: 0.82,
          clarity: 0.88,
          consistency: 0.75,
          accuracy: 0.90,
          relevance: 0.78,
          usability: 0.83
        },
        issueAnalysis: {
          criticalIssues: [],
          warnings: [
            {
              id: 'warn-1',
              type: 'content',
              severity: 'warning',
              title: 'Missing timestamps',
              description: 'Some conversation segments lack timestamp information',
              location: 'Multiple segments',
              fix: 'Add timestamp extraction from metadata',
              autoFixable: true
            }
          ],
          suggestions: [
            {
              id: 'sug-1',
              type: 'quality',
              severity: 'suggestion',
              title: 'Improve agent response clarity',
              description: 'Some agent responses could be more specific',
              location: 'Agent responses',
              fix: 'Use AI to suggest more detailed responses',
              autoFixable: false
            }
          ],
          totalIssues: 2
        },
        performanceMetrics: {
          processingTime: 1.2,
          extractionEfficiency: 0.78,
          expectedQuality: 0.82,
          resourceUsage: 0.45,
          optimizationPotential: 0.23
        },
        validatedAt: new Date().toISOString()
      }

      setValidationResults(mockResults)
      setValidationProgress(100)
      onValidationComplete?.(mockResults)

    } catch (error) {
      console.error('Validation failed:', error)
    } finally {
      setIsValidating(false)
    }
  }, [onValidationComplete])

  // Auto-validation effect
  useEffect(() => {
    if (autoValidation && content && !isValidating) {
      const timer = setTimeout(() => {
        performValidation()
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [content, autoValidation, isValidating, performValidation])

  // Handle section expansion
  const toggleSection = useCallback((section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }))
  }, [])

  // Handle issue fix
  const handleFixIssue = useCallback((issueId: string) => {
    if (!validationResults) return
    
    setValidationResults(prev => {
      if (!prev) return prev
      
      return {
        ...prev,
        issueAnalysis: {
          ...prev.issueAnalysis,
          warnings: prev.issueAnalysis.warnings.filter(issue => issue.id !== issueId),
          suggestions: prev.issueAnalysis.suggestions.filter(issue => issue.id !== issueId),
          totalIssues: prev.issueAnalysis.totalIssues - 1
        }
      }
    })
  }, [validationResults])

  // Handle recommendation application
  const handleApplyRecommendation = useCallback((recommendation: ProcessingRecommendation) => {
    onRecommendationApply?.(recommendation)
    
    // Remove applied recommendation
    setValidationResults(prev => {
      if (!prev) return prev
      
      return {
        ...prev,
        processingRecommendations: prev.processingRecommendations.filter(rec => rec.id !== recommendation.id)
      }
    })
  }, [onRecommendationApply])

  const overallScore = validationResults?.overallScore || 0
  const scoreColor = overallScore >= 0.8 ? 'text-green-600' : overallScore >= 0.6 ? 'text-yellow-600' : 'text-red-600'

  return (
    <div className={cn('h-full flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-medium flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Content Validation
          </h2>
          {validationResults && (
            <div className="flex items-center gap-2">
              <Badge variant="outline" className={cn('text-sm', scoreColor)}>
                {Math.round(overallScore * 100)}% Quality
              </Badge>
              <span className="text-xs text-muted-foreground">
                Validated {new Date(validationResults.validatedAt).toLocaleTimeString()}
              </span>
            </div>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2">
            <Switch
              id="auto-validation"
              checked={autoValidation}
              onCheckedChange={setAutoValidation}
            />
            <Label htmlFor="auto-validation" className="text-sm">
              Auto-validate
            </Label>
          </div>
          
          <Button
            variant="outline"
            size="sm"
            onClick={performValidation}
            disabled={isValidating || !content}
          >
            <RefreshCw className={cn('h-3 w-3 mr-1', isValidating && 'animate-spin')} />
            {isValidating ? 'Validating...' : 'Validate'}
          </Button>
        </div>
      </div>

      {/* Validation Progress */}
      {isValidating && (
        <div className="p-4 border-b">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="h-4 w-4 text-accent animate-pulse" />
            <span className="text-sm font-medium">Validating content...</span>
          </div>
          <Progress value={validationProgress} className="h-2" />
        </div>
      )}

      {/* Validation Results */}
      <ScrollArea className="flex-1 p-4">
        {validationResults ? (
          <div className="space-y-4">
            {/* Overall Score Card */}
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-medium">Overall Quality Score</h3>
                  <div className={cn('text-2xl font-bold', scoreColor)}>
                    {Math.round(overallScore * 100)}%
                  </div>
                </div>
                <Progress value={overallScore * 100} className="h-3 mb-2" />
                <div className="text-xs text-muted-foreground">
                  Based on content structure, quality metrics, and extractability
                </div>
              </CardContent>
            </Card>

            {/* Platform Detection */}
            {enablePlatformDetection && (
              <PlatformDetectionCard
                detection={validationResults.platformDetection}
                isExpanded={expandedSections.platform}
                onToggle={() => toggleSection('platform')}
              />
            )}

            {/* Quality Factors */}
            <Card>
              <CardHeader className="pb-3">
                <Collapsible open={expandedSections.quality} onOpenChange={() => toggleSection('quality')}>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" className="w-full justify-between p-0">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <Target className="h-4 w-4" />
                        Quality Factors
                      </CardTitle>
                      {expandedSections.quality ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </Button>
                  </CollapsibleTrigger>
                  
                  <CollapsibleContent className="space-y-3 pt-3">
                    {validationResults.contentQuality.factors.map(factor => (
                      <QualityFactorCard key={factor.name} factor={factor} showDetails />
                    ))}
                    
                    <Separator />
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <h4 className="text-sm font-medium mb-2 text-green-600">Strengths</h4>
                        <ul className="text-xs space-y-1">
                          {validationResults.contentQuality.strengths.map((strength, index) => (
                            <li key={index} className="flex items-center gap-1">
                              <CheckCircle2 className="h-3 w-3 text-green-500" />
                              {strength}
                            </li>
                          ))}
                        </ul>
                      </div>
                      
                      <div>
                        <h4 className="text-sm font-medium mb-2 text-yellow-600">Improvements</h4>
                        <ul className="text-xs space-y-1">
                          {validationResults.contentQuality.improvements.map((improvement, index) => (
                            <li key={index} className="flex items-center gap-1">
                              <AlertTriangle className="h-3 w-3 text-yellow-500" />
                              {improvement}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </CardHeader>
            </Card>

            {/* Quality Metrics Chart */}
            <QualityMetricsChart
              metrics={validationResults.qualityMetrics}
              isExpanded={expandedSections.metrics}
              onToggle={() => toggleSection('metrics')}
            />

            {/* Issues List */}
            <IssuesListCard
              analysis={validationResults.issueAnalysis}
              onFixIssue={handleFixIssue}
              isExpanded={expandedSections.issues}
              onToggle={() => toggleSection('issues')}
            />

            {/* Processing Recommendations */}
            <ProcessingRecommendationsCard
              recommendations={validationResults.processingRecommendations}
              onApply={handleApplyRecommendation}
              isExpanded={expandedSections.recommendations}
              onToggle={() => toggleSection('recommendations')}
            />

            {/* Performance Metrics */}
            <Card>
              <CardHeader className="pb-3">
                <Collapsible open={expandedSections.performance} onOpenChange={() => toggleSection('performance')}>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" className="w-full justify-between p-0">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <Activity className="h-4 w-4" />
                        Performance Metrics
                      </CardTitle>
                      {expandedSections.performance ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </Button>
                  </CollapsibleTrigger>
                  
                  <CollapsibleContent className="space-y-3 pt-3">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <div className="text-muted-foreground">Processing Time</div>
                        <div className="font-medium">{validationResults.performanceMetrics.processingTime}s</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Efficiency</div>
                        <div className="font-medium">{Math.round(validationResults.performanceMetrics.extractionEfficiency * 100)}%</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Resource Usage</div>
                        <div className="font-medium">{Math.round(validationResults.performanceMetrics.resourceUsage * 100)}%</div>
                      </div>
                      <div>
                        <div className="text-muted-foreground">Optimization Potential</div>
                        <div className="font-medium">{Math.round(validationResults.performanceMetrics.optimizationPotential * 100)}%</div>
                      </div>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </CardHeader>
            </Card>
          </div>
        ) : content ? (
          <div className="flex items-center justify-center h-32">
            <div className="text-center">
              <Shield className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <h3 className="text-lg font-medium mb-2">Ready for Validation</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Click "Validate" to analyze content quality and get improvement recommendations.
              </p>
              <Button onClick={performValidation}>
                <Shield className="h-4 w-4 mr-2" />
                Start Validation
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-32">
            <div className="text-center">
              <FileText className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <h3 className="text-lg font-medium mb-2">No Content to Validate</h3>
              <p className="text-sm text-muted-foreground">
                Please provide content to begin validation analysis.
              </p>
            </div>
          </div>
        )}
      </ScrollArea>

      {/* Status Bar */}
      {validationResults && (
        <div className="flex items-center justify-between p-2 border-t text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <span>{segments.length} segments analyzed</span>
            <span>{qaPairs.length} Q&A pairs evaluated</span>
          </div>
          <div className="flex items-center gap-4">
            <span>{validationResults.issueAnalysis.totalIssues} issues found</span>
            <span>{validationResults.processingRecommendations.length} recommendations</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default ValidationPanel