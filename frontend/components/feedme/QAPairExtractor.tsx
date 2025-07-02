/**
 * QAPairExtractor Component
 * 
 * AI-powered Q&A pair detection with confidence scoring visualization,
 * quality indicators with color coding, and suggested improvements panel.
 * 
 * Part of FeedMe v2.0 Phase 3C: Smart Conversation Editor
 */

'use client'

import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { 
  Brain, Eye, Edit3, Trash2, CheckCircle2, AlertCircle, 
  Clock, Wand2, TrendingUp, MessageCircle, Bot, User,
  ChevronDown, ChevronRight, Copy, Download, RefreshCw,
  Filter, SortAsc, Search, Plus, Minus, Star, Flag
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Slider } from '@/components/ui/slider'

// Types
interface QAPairExtractorProps {
  conversationId: number
  segments: ConversationSegment[]
  onExtractComplete?: (qaPairs: QAPair[]) => void
  onPairUpdate?: (pairId: string, updates: Partial<QAPair>) => void
  onPairDelete?: (pairId: string) => void
  enableRealTimeExtraction?: boolean
  minConfidenceThreshold?: number
  className?: string
}

interface ConversationSegment {
  id: string
  type: 'customer' | 'agent' | 'system' | 'metadata'
  speaker?: string
  content: string
  confidence: number
  timestamp?: string
}

interface QAPair {
  id: string
  question: string
  answer: string
  context: string[]
  confidence: number
  quality_score: number
  source_segments: string[]
  tags: string[]
  category: string
  issue_type: string
  resolution_type: string
  sentiment: 'positive' | 'neutral' | 'negative'
  usefulness_score: number
  is_approved: boolean
  is_flagged: boolean
  extraction_method: 'ai_detected' | 'manual_created' | 'ai_suggested'
  improvement_suggestions: ImprovementSuggestion[]
  validation_status: 'valid' | 'needs_review' | 'invalid'
  validation_message?: string
  created_at: string
  updated_at: string
}

interface ImprovementSuggestion {
  id: string
  type: 'clarity' | 'completeness' | 'accuracy' | 'formatting'
  severity: 'low' | 'medium' | 'high'
  description: string
  suggested_change: string
  confidence: number
}

interface ExtractionState {
  isExtracting: boolean
  progress: number
  currentStep: string
  extractedPairs: QAPair[]
  filteredPairs: QAPair[]
  selectedPairs: Set<string>
  editingPair: string | null
  searchQuery: string
  filterBy: 'all' | 'approved' | 'needs_review' | 'flagged'
  sortBy: 'confidence' | 'quality' | 'created_at' | 'usefulness'
  sortOrder: 'asc' | 'desc'
  confidenceThreshold: number
  qualityThreshold: number
}

// Quality Score Component
const QualityScoreIndicator: React.FC<{ 
  score: number, 
  size?: 'sm' | 'md' | 'lg',
  showLabel?: boolean 
}> = ({ score, size = 'md', showLabel = true }) => {
  const getColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600 bg-green-100'
    if (score >= 0.6) return 'text-yellow-600 bg-yellow-100'
    return 'text-red-600 bg-red-100'
  }

  const sizeClasses = {
    sm: 'h-6 w-12 text-xs',
    md: 'h-8 w-16 text-sm',
    lg: 'h-10 w-20 text-base'
  }

  return (
    <div className={cn('flex items-center gap-2')}>
      <div className={cn(
        'flex items-center justify-center rounded-full font-medium',
        getColor(score),
        sizeClasses[size]
      )}>
        {Math.round(score * 100)}%
      </div>
      {showLabel && <span className="text-xs text-muted-foreground">Quality</span>}
    </div>
  )
}

// Confidence Meter Component
const ConfidenceMeter: React.FC<{ 
  confidence: number,
  threshold?: number
}> = ({ confidence, threshold = 0.7 }) => {
  const percentage = confidence * 100
  const isAboveThreshold = confidence >= threshold
  
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <div className="flex items-center gap-2">
            <Progress 
              value={percentage} 
              className={cn(
                'w-16 h-2',
                isAboveThreshold ? 'bg-green-100' : 'bg-red-100'
              )}
            />
            <span className={cn(
              'text-xs font-medium',
              isAboveThreshold ? 'text-green-600' : 'text-red-600'
            )}>
              {Math.round(percentage)}%
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent>
          <p>AI Confidence: {Math.round(percentage)}%</p>
          <p>Threshold: {Math.round(threshold * 100)}%</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// Sentiment Badge Component
const SentimentBadge: React.FC<{ sentiment: QAPair['sentiment'] }> = ({ sentiment }) => {
  const config = {
    positive: { color: 'bg-green-100 text-green-800', label: 'Positive' },
    neutral: { color: 'bg-gray-100 text-gray-800', label: 'Neutral' },
    negative: { color: 'bg-red-100 text-red-800', label: 'Negative' }
  }

  return (
    <Badge variant="secondary" className={cn('text-xs', config[sentiment].color)}>
      {config[sentiment].label}
    </Badge>
  )
}

// Improvement Suggestions Panel
const ImprovementSuggestionsPanel: React.FC<{
  suggestions: ImprovementSuggestion[]
  onApply: (suggestionId: string) => void
  onDismiss: (suggestionId: string) => void
}> = ({ suggestions, onApply, onDismiss }) => {
  if (suggestions.length === 0) return null

  return (
    <Card className="mt-3">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Wand2 className="h-4 w-4" />
          Improvement Suggestions
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {suggestions.map(suggestion => (
          <div key={suggestion.id} className="p-3 border rounded-lg">
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <Badge 
                  variant="outline" 
                  className={cn(
                    'text-xs',
                    suggestion.severity === 'high' && 'border-red-500 text-red-700',
                    suggestion.severity === 'medium' && 'border-yellow-500 text-yellow-700',
                    suggestion.severity === 'low' && 'border-gray-500 text-gray-700'
                  )}
                >
                  {suggestion.type}
                </Badge>
                <Badge variant="secondary" className="text-xs">
                  {Math.round(suggestion.confidence * 100)}%
                </Badge>
              </div>
              <div className="flex gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onApply(suggestion.id)}
                  className="h-6 px-2 text-xs"
                >
                  Apply
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onDismiss(suggestion.id)}
                  className="h-6 px-2 text-xs"
                >
                  Dismiss
                </Button>
              </div>
            </div>
            <p className="text-sm text-muted-foreground mb-2">
              {suggestion.description}
            </p>
            <div className="text-sm p-2 bg-muted rounded">
              {suggestion.suggested_change}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// QA Pair Card Component
const QAPairCard: React.FC<{
  pair: QAPair
  isSelected: boolean
  isEditing: boolean
  onSelect: (id: string) => void
  onEdit: (id: string) => void
  onSave: (id: string, updates: Partial<QAPair>) => void
  onCancel: (id: string) => void
  onDelete: (id: string) => void
  onToggleApproval: (id: string) => void
  onToggleFlag: (id: string) => void
  onApplyImprovement: (pairId: string, suggestionId: string) => void
  onDismissImprovement: (pairId: string, suggestionId: string) => void
}> = ({
  pair,
  isSelected,
  isEditing,
  onSelect,
  onEdit,
  onSave,
  onCancel,
  onDelete,
  onToggleApproval,
  onToggleFlag,
  onApplyImprovement,
  onDismissImprovement
}) => {
  const [editQuestion, setEditQuestion] = useState(pair.question)
  const [editAnswer, setEditAnswer] = useState(pair.answer)
  const [isExpanded, setIsExpanded] = useState(false)

  const handleSave = useCallback(() => {
    onSave(pair.id, {
      question: editQuestion,
      answer: editAnswer,
      updated_at: new Date().toISOString()
    })
  }, [pair.id, editQuestion, editAnswer, onSave])

  const handleCancel = useCallback(() => {
    setEditQuestion(pair.question)
    setEditAnswer(pair.answer)
    onCancel(pair.id)
  }, [pair.id, pair.question, pair.answer, onCancel])

  return (
    <Card 
      className={cn(
        'mb-4 transition-all duration-200',
        isSelected && 'ring-2 ring-accent shadow-md',
        pair.is_flagged && 'border-red-300',
        pair.is_approved && 'border-green-300',
        'hover:shadow-sm cursor-pointer'
      )}
      onClick={() => !isEditing && onSelect(pair.id)}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <Checkbox
              checked={isSelected}
              onChange={() => onSelect(pair.id)}
              onClick={(e) => e.stopPropagation()}
            />
            <Badge variant="outline" className="text-xs shrink-0">
              {pair.extraction_method.replace('_', ' ')}
            </Badge>
            <Badge variant="secondary" className="text-xs shrink-0">
              {pair.category}
            </Badge>
            <SentimentBadge sentiment={pair.sentiment} />
            {pair.validation_status !== 'valid' && (
              <Badge variant="destructive" className="text-xs">
                {pair.validation_status.replace('_', ' ')}
              </Badge>
            )}
          </div>
          
          <div className="flex items-center gap-1 shrink-0">
            <QualityScoreIndicator score={pair.quality_score} size="sm" showLabel={false} />
            <ConfidenceMeter confidence={pair.confidence} />
            
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onToggleApproval(pair.id)
              }}
              className={cn(
                'h-6 w-6 p-0',
                pair.is_approved && 'text-green-600'
              )}
            >
              <CheckCircle2 className="h-3 w-3" />
            </Button>
            
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onToggleFlag(pair.id)
              }}
              className={cn(
                'h-6 w-6 p-0',
                pair.is_flagged && 'text-red-600'
              )}
            >
              <Flag className="h-3 w-3" />
            </Button>
            
            {!isEditing && (
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  onEdit(pair.id)
                }}
                className="h-6 w-6 p-0"
              >
                <Edit3 className="h-3 w-3" />
              </Button>
            )}
            
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(pair.id)
              }}
              className="h-6 w-6 p-0 text-destructive"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Question */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <User className="h-3 w-3 text-blue-500" />
            <span className="text-xs font-medium text-muted-foreground">QUESTION</span>
          </div>
          {isEditing ? (
            <Textarea
              value={editQuestion}
              onChange={(e) => setEditQuestion(e.target.value)}
              className="min-h-[60px] text-sm"
              placeholder="Enter question..."
            />
          ) : (
            <p className="text-sm leading-relaxed">{pair.question}</p>
          )}
        </div>

        {/* Answer */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <MessageCircle className="h-3 w-3 text-green-500" />
            <span className="text-xs font-medium text-muted-foreground">ANSWER</span>
          </div>
          {isEditing ? (
            <Textarea
              value={editAnswer}
              onChange={(e) => setEditAnswer(e.target.value)}
              className="min-h-[80px] text-sm"
              placeholder="Enter answer..."
            />
          ) : (
            <p className="text-sm leading-relaxed">{pair.answer}</p>
          )}
        </div>

        {/* Edit Controls */}
        {isEditing && (
          <div className="flex items-center gap-2 pt-2 border-t">
            <Button variant="default" size="sm" onClick={handleSave}>
              <CheckCircle2 className="h-3 w-3 mr-1" />
              Save
            </Button>
            <Button variant="ghost" size="sm" onClick={handleCancel}>
              Cancel
            </Button>
          </div>
        )}

        {/* Expandable Details */}
        <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" className="w-full justify-between p-0 h-auto">
              <span className="text-xs text-muted-foreground">
                {isExpanded ? 'Hide details' : 'Show details'}
              </span>
              {isExpanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
            </Button>
          </CollapsibleTrigger>
          
          <CollapsibleContent className="space-y-3 pt-3">
            {/* Tags and Metadata */}
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <span className="text-muted-foreground">Issue Type:</span>
                <div className="font-medium">{pair.issue_type}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Resolution:</span>
                <div className="font-medium">{pair.resolution_type}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Usefulness:</span>
                <div className="flex items-center gap-1">
                  <Star className="h-3 w-3 text-yellow-500" />
                  <span className="font-medium">{Math.round(pair.usefulness_score * 100)}%</span>
                </div>
              </div>
              <div>
                <span className="text-muted-foreground">Created:</span>
                <div className="font-medium">
                  {new Date(pair.created_at).toLocaleDateString()}
                </div>
              </div>
            </div>

            {/* Tags */}
            {pair.tags.length > 0 && (
              <div>
                <span className="text-xs text-muted-foreground mb-1 block">Tags:</span>
                <div className="flex gap-1 flex-wrap">
                  {pair.tags.map(tag => (
                    <Badge key={tag} variant="outline" className="text-xs">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Context */}
            {pair.context.length > 0 && (
              <div>
                <span className="text-xs text-muted-foreground mb-1 block">Context:</span>
                <div className="text-xs text-muted-foreground space-y-1">
                  {pair.context.map((ctx, index) => (
                    <div key={index} className="pl-2 border-l-2 border-muted">
                      {ctx}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Improvement Suggestions */}
            <ImprovementSuggestionsPanel
              suggestions={pair.improvement_suggestions}
              onApply={(suggestionId) => onApplyImprovement(pair.id, suggestionId)}
              onDismiss={(suggestionId) => onDismissImprovement(pair.id, suggestionId)}
            />
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  )
}

// Extraction Progress Panel
const ExtractionProgressPanel: React.FC<{
  isExtracting: boolean
  progress: number
  currentStep: string
  onCancel: () => void
}> = ({ isExtracting, progress, currentStep, onCancel }) => {
  if (!isExtracting) return null

  return (
    <Card className="mb-4">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-accent animate-pulse" />
            <span className="font-medium text-sm">Extracting Q&A Pairs</span>
          </div>
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        </div>
        
        <Progress value={progress} className="mb-2" />
        
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{currentStep}</span>
          <span>{Math.round(progress)}%</span>
        </div>
      </CardContent>
    </Card>
  )
}

// Main Component
export const QAPairExtractor: React.FC<QAPairExtractorProps> = ({
  conversationId,
  segments,
  onExtractComplete,
  onPairUpdate,
  onPairDelete,
  enableRealTimeExtraction = true,
  minConfidenceThreshold = 0.7,
  className
}) => {
  const [state, setState] = useState<ExtractionState>({
    isExtracting: false,
    progress: 0,
    currentStep: '',
    extractedPairs: [],
    filteredPairs: [],
    selectedPairs: new Set(),
    editingPair: null,
    searchQuery: '',
    filterBy: 'all',
    sortBy: 'confidence',
    sortOrder: 'desc',
    confidenceThreshold: minConfidenceThreshold,
    qualityThreshold: 0.6
  })

  // Filter and sort pairs
  const filteredAndSortedPairs = useMemo(() => {
    let filtered = [...state.extractedPairs]

    // Search filter
    if (state.searchQuery.trim()) {
      const query = state.searchQuery.toLowerCase()
      filtered = filtered.filter(pair => 
        pair.question.toLowerCase().includes(query) ||
        pair.answer.toLowerCase().includes(query) ||
        pair.tags.some(tag => tag.toLowerCase().includes(query))
      )
    }

    // Status filter
    switch (state.filterBy) {
      case 'approved':
        filtered = filtered.filter(pair => pair.is_approved)
        break
      case 'needs_review':
        filtered = filtered.filter(pair => pair.validation_status === 'needs_review')
        break
      case 'flagged':
        filtered = filtered.filter(pair => pair.is_flagged)
        break
    }

    // Threshold filters
    filtered = filtered.filter(pair => 
      pair.confidence >= state.confidenceThreshold &&
      pair.quality_score >= state.qualityThreshold
    )

    // Sort
    filtered.sort((a, b) => {
      const multiplier = state.sortOrder === 'asc' ? 1 : -1
      
      switch (state.sortBy) {
        case 'confidence':
          return (a.confidence - b.confidence) * multiplier
        case 'quality':
          return (a.quality_score - b.quality_score) * multiplier
        case 'created_at':
          return (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()) * multiplier
        case 'usefulness':
          return (a.usefulness_score - b.usefulness_score) * multiplier
        default:
          return 0
      }
    })

    return filtered
  }, [state.extractedPairs, state.searchQuery, state.filterBy, state.sortBy, state.sortOrder, state.confidenceThreshold, state.qualityThreshold])

  // Start extraction
  const handleStartExtraction = useCallback(async () => {
    setState(prev => ({ 
      ...prev, 
      isExtracting: true, 
      progress: 0,
      currentStep: 'Analyzing conversation structure...'
    }))

    try {
      const steps = [
        'Analyzing conversation structure...',
        'Identifying question-answer patterns...',
        'Extracting potential Q&A pairs...',
        'Analyzing context and quality...',
        'Generating improvement suggestions...',
        'Finalizing extraction...'
      ]

      for (let i = 0; i < steps.length; i++) {
        setState(prev => ({ 
          ...prev, 
          progress: (i / steps.length) * 100,
          currentStep: steps[i]
        }))
        
        await new Promise(resolve => setTimeout(resolve, 1000))
      }

      // Mock extracted pairs
      const mockPairs: QAPair[] = [
        {
          id: 'qa-1',
          question: 'How do I sync my emails with Mailbird?',
          answer: 'To sync your emails with Mailbird, go to Account Settings and click on the Sync tab. Make sure your internet connection is stable and click "Sync Now".',
          context: ['Previous sync failed', 'User has IMAP account'],
          confidence: 0.92,
          quality_score: 0.85,
          source_segments: ['seg-1', 'seg-3'],
          tags: ['sync', 'email', 'settings'],
          category: 'Technical Support',
          issue_type: 'Sync Issues',
          resolution_type: 'Configuration',
          sentiment: 'neutral',
          usefulness_score: 0.88,
          is_approved: false,
          is_flagged: false,
          extraction_method: 'ai_detected',
          improvement_suggestions: [{
            id: 'imp-1',
            type: 'clarity',
            severity: 'medium',
            description: 'Consider adding more specific steps',
            suggested_change: 'Add numbered steps for the sync process',
            confidence: 0.75
          }],
          validation_status: 'valid',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        },
        {
          id: 'qa-2',
          question: 'Why are my emails not loading?',
          answer: 'Email loading issues can be caused by network connectivity problems or server issues. Please check your internet connection and try refreshing the application.',
          context: ['User experiencing slow loading', 'Multiple account setup'],
          confidence: 0.78,
          quality_score: 0.72,
          source_segments: ['seg-2', 'seg-4'],
          tags: ['loading', 'connectivity', 'troubleshooting'],
          category: 'Technical Support',
          issue_type: 'Performance',
          resolution_type: 'Troubleshooting',
          sentiment: 'negative',
          usefulness_score: 0.81,
          is_approved: false,
          is_flagged: false,
          extraction_method: 'ai_detected',
          improvement_suggestions: [{
            id: 'imp-2',
            type: 'completeness',
            severity: 'high',
            description: 'Missing advanced troubleshooting steps',
            suggested_change: 'Add steps for checking account settings and clearing cache',
            confidence: 0.82
          }],
          validation_status: 'needs_review',
          validation_message: 'Answer could be more comprehensive',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }
      ]

      setState(prev => ({ 
        ...prev, 
        isExtracting: false,
        progress: 100,
        extractedPairs: mockPairs,
        filteredPairs: mockPairs
      }))

      onExtractComplete?.(mockPairs)

    } catch (error) {
      setState(prev => ({ 
        ...prev, 
        isExtracting: false,
        progress: 0,
        currentStep: 'Extraction failed'
      }))
    }
  }, [onExtractComplete])

  // Handle pair selection
  const handlePairSelect = useCallback((pairId: string) => {
    setState(prev => {
      const newSelected = new Set(prev.selectedPairs)
      if (newSelected.has(pairId)) {
        newSelected.delete(pairId)
      } else {
        newSelected.add(pairId)
      }
      return { ...prev, selectedPairs: newSelected }
    })
  }, [])

  // Handle pair editing
  const handlePairEdit = useCallback((pairId: string) => {
    setState(prev => ({ ...prev, editingPair: pairId }))
  }, [])

  // Handle pair save
  const handlePairSave = useCallback((pairId: string, updates: Partial<QAPair>) => {
    setState(prev => ({
      ...prev,
      extractedPairs: prev.extractedPairs.map(pair =>
        pair.id === pairId ? { ...pair, ...updates } : pair
      ),
      editingPair: null
    }))
    onPairUpdate?.(pairId, updates)
  }, [onPairUpdate])

  // Handle pair cancel
  const handlePairCancel = useCallback((pairId: string) => {
    setState(prev => ({ ...prev, editingPair: null }))
  }, [])

  // Handle pair delete
  const handlePairDelete = useCallback((pairId: string) => {
    if (window.confirm('Are you sure you want to delete this Q&A pair?')) {
      setState(prev => ({
        ...prev,
        extractedPairs: prev.extractedPairs.filter(pair => pair.id !== pairId),
        selectedPairs: new Set([...prev.selectedPairs].filter(id => id !== pairId))
      }))
      onPairDelete?.(pairId)
    }
  }, [onPairDelete])

  // Handle approval toggle
  const handleToggleApproval = useCallback((pairId: string) => {
    setState(prev => ({
      ...prev,
      extractedPairs: prev.extractedPairs.map(pair =>
        pair.id === pairId ? { ...pair, is_approved: !pair.is_approved } : pair
      )
    }))
  }, [])

  // Handle flag toggle
  const handleToggleFlag = useCallback((pairId: string) => {
    setState(prev => ({
      ...prev,
      extractedPairs: prev.extractedPairs.map(pair =>
        pair.id === pairId ? { ...pair, is_flagged: !pair.is_flagged } : pair
      )
    }))
  }, [])

  // Handle improvement application
  const handleApplyImprovement = useCallback((pairId: string, suggestionId: string) => {
    setState(prev => ({
      ...prev,
      extractedPairs: prev.extractedPairs.map(pair => {
        if (pair.id === pairId) {
          const suggestion = pair.improvement_suggestions.find(s => s.id === suggestionId)
          if (suggestion) {
            // Apply the suggestion (simplified)
            return {
              ...pair,
              improvement_suggestions: pair.improvement_suggestions.filter(s => s.id !== suggestionId),
              quality_score: Math.min(1.0, pair.quality_score + 0.1)
            }
          }
        }
        return pair
      })
    }))
  }, [])

  // Handle improvement dismissal
  const handleDismissImprovement = useCallback((pairId: string, suggestionId: string) => {
    setState(prev => ({
      ...prev,
      extractedPairs: prev.extractedPairs.map(pair =>
        pair.id === pairId 
          ? {
              ...pair,
              improvement_suggestions: pair.improvement_suggestions.filter(s => s.id !== suggestionId)
            }
          : pair
      )
    }))
  }, [])

  // Handle bulk approval
  const handleBulkApprove = useCallback(() => {
    setState(prev => ({
      ...prev,
      extractedPairs: prev.extractedPairs.map(pair =>
        prev.selectedPairs.has(pair.id) ? { ...pair, is_approved: true } : pair
      ),
      selectedPairs: new Set()
    }))
  }, [])

  // Handle export
  const handleExport = useCallback(() => {
    const exportData = {
      conversationId,
      qaPairs: state.extractedPairs,
      exportedAt: new Date().toISOString()
    }
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `qa-pairs-${conversationId}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [conversationId, state.extractedPairs])

  const stats = useMemo(() => {
    const total = state.extractedPairs.length
    const approved = state.extractedPairs.filter(p => p.is_approved).length
    const needsReview = state.extractedPairs.filter(p => p.validation_status === 'needs_review').length
    const flagged = state.extractedPairs.filter(p => p.is_flagged).length
    const avgQuality = total > 0 ? state.extractedPairs.reduce((sum, p) => sum + p.quality_score, 0) / total : 0
    
    return { total, approved, needsReview, flagged, avgQuality }
  }, [state.extractedPairs])

  return (
    <div className={cn('h-full flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-medium flex items-center gap-2">
            <Brain className="h-5 w-5" />
            Q&A Pair Extractor
          </h2>
          {stats.total > 0 && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Badge variant="secondary">{stats.total} pairs</Badge>
              <Badge variant="outline">{stats.approved} approved</Badge>
              <Badge variant="outline">{Math.round(stats.avgQuality * 100)}% avg quality</Badge>
            </div>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {state.selectedPairs.size > 0 && (
            <>
              <Button variant="outline" size="sm" onClick={handleBulkApprove}>
                Approve Selected ({state.selectedPairs.size})
              </Button>
              <Separator orientation="vertical" className="h-4" />
            </>
          )}
          
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={state.extractedPairs.length === 0}
          >
            <Download className="h-3 w-3 mr-1" />
            Export
          </Button>
          
          <Button
            variant="default"
            size="sm"
            onClick={handleStartExtraction}
            disabled={state.isExtracting || segments.length === 0}
          >
            <Brain className="h-3 w-3 mr-1" />
            {state.extractedPairs.length > 0 ? 'Re-extract' : 'Extract Q&A Pairs'}
          </Button>
        </div>
      </div>

      {/* Extraction Progress */}
      <ExtractionProgressPanel
        isExtracting={state.isExtracting}
        progress={state.progress}
        currentStep={state.currentStep}
        onCancel={() => setState(prev => ({ ...prev, isExtracting: false }))}
      />

      {/* Filters and Controls */}
      {state.extractedPairs.length > 0 && (
        <div className="p-4 border-b space-y-3">
          {/* Search and Filter Bar */}
          <div className="flex items-center gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-muted-foreground" />
              <Input
                placeholder="Search Q&A pairs..."
                value={state.searchQuery}
                onChange={(e) => setState(prev => ({ ...prev, searchQuery: e.target.value }))}
                className="pl-7"
              />
            </div>
            
            <Select value={state.filterBy} onValueChange={(value: any) => setState(prev => ({ ...prev, filterBy: value }))}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All pairs</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
                <SelectItem value="needs_review">Needs review</SelectItem>
                <SelectItem value="flagged">Flagged</SelectItem>
              </SelectContent>
            </Select>
            
            <Select value={state.sortBy} onValueChange={(value: any) => setState(prev => ({ ...prev, sortBy: value }))}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="confidence">Confidence</SelectItem>
                <SelectItem value="quality">Quality</SelectItem>
                <SelectItem value="usefulness">Usefulness</SelectItem>
                <SelectItem value="created_at">Date</SelectItem>
              </SelectContent>
            </Select>
            
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setState(prev => ({ 
                ...prev, 
                sortOrder: prev.sortOrder === 'asc' ? 'desc' : 'asc' 
              }))}
            >
              <SortAsc className={cn('h-3 w-3', state.sortOrder === 'desc' && 'rotate-180')} />
            </Button>
          </div>

          {/* Threshold Controls */}
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">Confidence:</span>
              <Slider
                value={[state.confidenceThreshold]}
                onValueChange={([value]) => setState(prev => ({ ...prev, confidenceThreshold: value }))}
                max={1}
                min={0}
                step={0.05}
                className="w-24"
              />
              <span className="text-xs w-8">{Math.round(state.confidenceThreshold * 100)}%</span>
            </div>
            
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted-foreground">Quality:</span>
              <Slider
                value={[state.qualityThreshold]}
                onValueChange={([value]) => setState(prev => ({ ...prev, qualityThreshold: value }))}
                max={1}
                min={0}
                step={0.05}
                className="w-24"
              />
              <span className="text-xs w-8">{Math.round(state.qualityThreshold * 100)}%</span>
            </div>
          </div>
        </div>
      )}

      {/* Q&A Pairs List */}
      <ScrollArea className="flex-1 p-4">
        {filteredAndSortedPairs.length > 0 ? (
          <div className="space-y-4">
            {filteredAndSortedPairs.map(pair => (
              <QAPairCard
                key={pair.id}
                pair={pair}
                isSelected={state.selectedPairs.has(pair.id)}
                isEditing={state.editingPair === pair.id}
                onSelect={handlePairSelect}
                onEdit={handlePairEdit}
                onSave={handlePairSave}
                onCancel={handlePairCancel}
                onDelete={handlePairDelete}
                onToggleApproval={handleToggleApproval}
                onToggleFlag={handleToggleFlag}
                onApplyImprovement={handleApplyImprovement}
                onDismissImprovement={handleDismissImprovement}
              />
            ))}
          </div>
        ) : state.extractedPairs.length > 0 ? (
          <div className="flex items-center justify-center h-32">
            <div className="text-center">
              <Filter className="h-8 w-8 mx-auto mb-2 text-muted-foreground opacity-50" />
              <p className="text-sm text-muted-foreground">No pairs match the current filters</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setState(prev => ({ 
                  ...prev, 
                  searchQuery: '', 
                  filterBy: 'all',
                  confidenceThreshold: 0,
                  qualityThreshold: 0
                }))}
                className="mt-2"
              >
                Clear filters
              </Button>
            </div>
          </div>
        ) : segments.length > 0 ? (
          <div className="flex items-center justify-center h-32">
            <div className="text-center">
              <Brain className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <h3 className="text-lg font-medium mb-2">Ready to Extract Q&A Pairs</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Click "Extract Q&A Pairs" to analyze the conversation and identify potential question-answer pairs.
              </p>
              <Button onClick={handleStartExtraction}>
                <Brain className="h-4 w-4 mr-2" />
                Start Extraction
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-32">
            <div className="text-center">
              <MessageCircle className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <h3 className="text-lg font-medium mb-2">No Conversation Segments</h3>
              <p className="text-sm text-muted-foreground">
                Please provide conversation segments to extract Q&A pairs.
              </p>
            </div>
          </div>
        )}
      </ScrollArea>

      {/* Status Bar */}
      <div className="flex items-center justify-between p-2 border-t text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <span>{filteredAndSortedPairs.length} of {state.extractedPairs.length} pairs shown</span>
          {state.selectedPairs.size > 0 && (
            <span>{state.selectedPairs.size} selected</span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <span>{stats.approved} approved</span>
          <span>{stats.needsReview} need review</span>
          {stats.flagged > 0 && <span>{stats.flagged} flagged</span>}
        </div>
      </div>
    </div>
  )
}

export default QAPairExtractor