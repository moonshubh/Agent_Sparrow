/**
 * ConversationEditor Component
 * 
 * Split-pane layout with original vs. AI-extracted content,
 * real-time AI preview with debounced updates, conversation segmentation,
 * and click-to-edit segments with inline validation.
 * 
 * Part of FeedMe v2.0 Phase 3C: Smart Conversation Editor
 */

'use client'

import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable'
import { 
  Eye, Edit3, Save, X, RefreshCw, Wand2, CheckCircle2, 
  AlertCircle, Clock, FileText, MessageSquare, Bot, User,
  ChevronRight, ChevronDown, Copy, Download, Undo, Redo
} from 'lucide-react'
import { useDebounce } from '@/hooks/use-debounce'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'

// Types
interface ConversationEditorProps {
  conversationId: number
  originalContent: string
  extractedContent?: ConversationSegment[]
  onSave?: (content: ConversationSegment[]) => void
  onCancel?: () => void
  enableAIPreview?: boolean
  enableRealTimeUpdates?: boolean
  className?: string
}

interface ConversationSegment {
  id: string
  type: 'customer' | 'agent' | 'system' | 'metadata'
  speaker?: string
  timestamp?: string
  content: string
  confidence: number
  isEditing?: boolean
  hasChanges?: boolean
  aiSuggestions?: AISuggestion[]
  validationStatus: 'valid' | 'warning' | 'error'
  validationMessage?: string
}

interface AISuggestion {
  id: string
  type: 'grammar' | 'clarity' | 'segmentation' | 'speaker_detection'
  original: string
  suggested: string
  confidence: number
  reason: string
}

interface EditorState {
  segments: ConversationSegment[]
  selectedSegmentId: string | null
  isPreviewMode: boolean
  isAutoSaving: boolean
  hasUnsavedChanges: boolean
  undoStack: ConversationSegment[][]
  redoStack: ConversationSegment[][]
  aiPreviewProgress: number
  validationResults: ValidationResult[]
}

interface ValidationResult {
  segmentId: string
  type: 'error' | 'warning' | 'info'
  message: string
  suggestion?: string
}

// Validation Badge Component
const ValidationBadge: React.FC<{ 
  status: ConversationSegment['validationStatus'],
  message?: string,
  size?: 'sm' | 'md'
}> = ({ status, message, size = 'sm' }) => {
  const badgeSize = size === 'sm' ? 'h-3 w-3' : 'h-4 w-4'
  
  if (status === 'valid') {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <CheckCircle2 className={cn(badgeSize, 'text-green-500')} />
          </TooltipTrigger>
          <TooltipContent>
            <p>Valid segment</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }
  
  if (status === 'warning') {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <AlertCircle className={cn(badgeSize, 'text-yellow-500')} />
          </TooltipTrigger>
          <TooltipContent>
            <p>{message || 'Validation warning'}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }
  
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <AlertCircle className={cn(badgeSize, 'text-red-500')} />
        </TooltipTrigger>
        <TooltipContent>
          <p>{message || 'Validation error'}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// Speaker Icon Component
const SpeakerIcon: React.FC<{ type: ConversationSegment['type'] }> = ({ type }) => {
  switch (type) {
    case 'customer':
      return <User className="h-4 w-4 text-blue-500" />
    case 'agent':
      return <MessageSquare className="h-4 w-4 text-green-500" />
    case 'system':
      return <Bot className="h-4 w-4 text-gray-500" />
    default:
      return <FileText className="h-4 w-4 text-gray-400" />
  }
}

// Segment Component
const SegmentComponent: React.FC<{
  segment: ConversationSegment
  isSelected: boolean
  isEditing: boolean
  onSelect: (id: string) => void
  onEdit: (id: string, content: string) => void
  onSave: (id: string) => void
  onCancel: (id: string) => void
  onApplySuggestion: (segmentId: string, suggestionId: string) => void
}> = ({ 
  segment, 
  isSelected, 
  isEditing, 
  onSelect, 
  onEdit, 
  onSave, 
  onCancel,
  onApplySuggestion
}) => {
  const [editContent, setEditContent] = useState(segment.content)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus()
      textareaRef.current.select()
    }
  }, [isEditing])

  const handleSave = useCallback(() => {
    onEdit(segment.id, editContent)
    onSave(segment.id)
  }, [segment.id, editContent, onEdit, onSave])

  const handleCancel = useCallback(() => {
    setEditContent(segment.content)
    onCancel(segment.id)
  }, [segment.id, segment.content, onCancel])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSave()
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      handleCancel()
    }
  }, [handleSave, handleCancel])

  return (
    <Card 
      className={cn(
        'mb-3 cursor-pointer transition-all duration-200',
        isSelected && 'ring-2 ring-accent shadow-md',
        segment.hasChanges && 'border-yellow-500',
        'hover:shadow-sm'
      )}
      onClick={() => !isEditing && onSelect(segment.id)}
    >
      <CardContent className="p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <SpeakerIcon type={segment.type} />
            <span className="text-sm font-medium capitalize">
              {segment.speaker || segment.type}
            </span>
            {segment.timestamp && (
              <span className="text-xs text-muted-foreground">
                {new Date(segment.timestamp).toLocaleTimeString()}
              </span>
            )}
            <ValidationBadge 
              status={segment.validationStatus} 
              message={segment.validationMessage}
            />
            {segment.hasChanges && (
              <Badge variant="secondary" className="text-xs">
                Modified
              </Badge>
            )}
          </div>
          
          <div className="flex items-center gap-1">
            <Badge variant="outline" className="text-xs">
              {Math.round(segment.confidence * 100)}%
            </Badge>
            {isSelected && !isEditing && (
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  onSelect(segment.id)
                }}
              >
                <Edit3 className="h-3 w-3" />
              </Button>
            )}
          </div>
        </div>

        {/* Content */}
        {isEditing ? (
          <div className="space-y-2">
            <Textarea
              ref={textareaRef}
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              onKeyDown={handleKeyDown}
              className="min-h-[100px] resize-y"
              placeholder="Enter conversation content..."
            />
            <div className="flex items-center justify-between">
              <div className="text-xs text-muted-foreground">
                Press Ctrl+Enter to save, Escape to cancel
              </div>
              <div className="flex gap-1">
                <Button variant="ghost" size="sm" onClick={handleCancel}>
                  <X className="h-3 w-3" />
                </Button>
                <Button variant="default" size="sm" onClick={handleSave}>
                  <Save className="h-3 w-3" />
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="whitespace-pre-wrap text-sm leading-relaxed">
            {segment.content}
          </div>
        )}

        {/* AI Suggestions */}
        {segment.aiSuggestions && segment.aiSuggestions.length > 0 && isSelected && (
          <div className="mt-3 pt-3 border-t">
            <h4 className="text-xs font-medium mb-2 flex items-center gap-1">
              <Wand2 className="h-3 w-3" />
              AI Suggestions
            </h4>
            <div className="space-y-2">
              {segment.aiSuggestions.map(suggestion => (
                <div key={suggestion.id} className="p-2 bg-muted/50 rounded text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium capitalize">
                      {suggestion.type.replace('_', ' ')}
                    </span>
                    <Badge variant="outline" className="text-xs">
                      {Math.round(suggestion.confidence * 100)}%
                    </Badge>
                  </div>
                  <div className="mb-1 text-muted-foreground">
                    {suggestion.reason}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-red-600">- {suggestion.original}</span>
                    <ChevronRight className="h-3 w-3" />
                    <span className="text-green-600">+ {suggestion.suggested}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onApplySuggestion(segment.id, suggestion.id)}
                      className="ml-auto h-6 px-2"
                    >
                      Apply
                    </Button>
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

// AI Preview Panel
const AIPreviewPanel: React.FC<{
  segments: ConversationSegment[]
  isLoading: boolean
  progress: number
  onRefresh: () => void
}> = ({ segments, isLoading, progress, onRefresh }) => {
  const stats = useMemo(() => {
    const total = segments.length
    const customerMessages = segments.filter(s => s.type === 'customer').length
    const agentMessages = segments.filter(s => s.type === 'agent').length
    const avgConfidence = segments.reduce((sum, s) => sum + s.confidence, 0) / total || 0
    const issues = segments.filter(s => s.validationStatus !== 'valid').length
    
    return { total, customerMessages, agentMessages, avgConfidence, issues }
  }, [segments])

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <Bot className="h-4 w-4" />
            AI Analysis
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRefresh}
            disabled={isLoading}
          >
            <RefreshCw className={cn('h-3 w-3', isLoading && 'animate-spin')} />
          </Button>
        </div>
        {isLoading && (
          <Progress value={progress} className="h-1" />
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <div className="text-muted-foreground">Total Segments</div>
            <div className="font-medium">{stats.total}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Avg Confidence</div>
            <div className="font-medium">{Math.round(stats.avgConfidence * 100)}%</div>
          </div>
          <div>
            <div className="text-muted-foreground">Customer</div>
            <div className="font-medium text-blue-600">{stats.customerMessages}</div>
          </div>
          <div>
            <div className="text-muted-foreground">Agent</div>
            <div className="font-medium text-green-600">{stats.agentMessages}</div>
          </div>
        </div>
        
        {stats.issues > 0 && (
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {stats.issues} segment{stats.issues === 1 ? '' : 's'} need{stats.issues === 1 ? 's' : ''} attention
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}

// Editor Toolbar
const EditorToolbar: React.FC<{
  hasUnsavedChanges: boolean
  canUndo: boolean
  canRedo: boolean
  isPreviewMode: boolean
  onSave: () => void
  onUndo: () => void
  onRedo: () => void
  onTogglePreview: () => void
  onExport: () => void
  onAutoSaveToggle: (enabled: boolean) => void
  autoSaveEnabled: boolean
}> = ({ 
  hasUnsavedChanges, 
  canUndo, 
  canRedo, 
  isPreviewMode, 
  onSave, 
  onUndo, 
  onRedo, 
  onTogglePreview, 
  onExport,
  onAutoSaveToggle,
  autoSaveEnabled
}) => {
  return (
    <div className="flex items-center justify-between p-3 border-b">
      <div className="flex items-center gap-2">
        <Button
          variant="default"
          size="sm"
          onClick={onSave}
          disabled={!hasUnsavedChanges}
        >
          <Save className="h-3 w-3 mr-1" />
          Save
        </Button>
        
        <Separator orientation="vertical" className="h-4" />
        
        <Button
          variant="ghost"
          size="sm"
          onClick={onUndo}
          disabled={!canUndo}
        >
          <Undo className="h-3 w-3" />
        </Button>
        
        <Button
          variant="ghost"
          size="sm"
          onClick={onRedo}
          disabled={!canRedo}
        >
          <Redo className="h-3 w-3" />
        </Button>
        
        <Separator orientation="vertical" className="h-4" />
        
        <Button
          variant={isPreviewMode ? "default" : "ghost"}
          size="sm"
          onClick={onTogglePreview}
        >
          <Eye className="h-3 w-3 mr-1" />
          Preview
        </Button>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <Switch
            id="auto-save"
            checked={autoSaveEnabled}
            onCheckedChange={onAutoSaveToggle}
          />
          <Label htmlFor="auto-save" className="text-sm">
            Auto-save
          </Label>
        </div>
        
        <Button
          variant="ghost"
          size="sm"
          onClick={onExport}
        >
          <Download className="h-3 w-3 mr-1" />
          Export
        </Button>
      </div>
    </div>
  )
}

// Main Component
export const ConversationEditor: React.FC<ConversationEditorProps> = ({
  conversationId,
  originalContent,
  extractedContent = [],
  onSave,
  onCancel,
  enableAIPreview = true,
  enableRealTimeUpdates = true,
  className
}) => {
  const [editorState, setEditorState] = useState<EditorState>({
    segments: extractedContent.length > 0 ? extractedContent : [{
      id: 'original',
      type: 'metadata',
      content: originalContent,
      confidence: 1.0,
      validationStatus: 'valid'
    }],
    selectedSegmentId: null,
    isPreviewMode: false,
    isAutoSaving: false,
    hasUnsavedChanges: false,
    undoStack: [],
    redoStack: [],
    aiPreviewProgress: 0,
    validationResults: []
  })

  const [autoSaveEnabled, setAutoSaveEnabled] = useState(true)
  const [aiProcessing, setAiProcessing] = useState(false)
  
  // Debounced auto-save
  const debouncedSegments = useDebounce(editorState.segments, 2000)
  
  useEffect(() => {
    if (autoSaveEnabled && editorState.hasUnsavedChanges && !aiProcessing) {
      handleAutoSave()
    }
  }, [debouncedSegments, autoSaveEnabled, editorState.hasUnsavedChanges, aiProcessing])

  // Handle segment selection
  const handleSegmentSelect = useCallback((segmentId: string) => {
    setEditorState(prev => ({
      ...prev,
      selectedSegmentId: prev.selectedSegmentId === segmentId ? null : segmentId,
      segments: prev.segments.map(s => ({ ...s, isEditing: false }))
    }))
  }, [])

  // Handle segment editing
  const handleSegmentEdit = useCallback((segmentId: string, content: string) => {
    setEditorState(prev => {
      const newSegments = prev.segments.map(s => 
        s.id === segmentId 
          ? { ...s, content, hasChanges: true, isEditing: true }
          : s
      )
      
      return {
        ...prev,
        segments: newSegments,
        hasUnsavedChanges: true,
        undoStack: [...prev.undoStack.slice(-9), prev.segments], // Keep last 10
        redoStack: []
      }
    })
  }, [])

  // Handle segment save
  const handleSegmentSave = useCallback((segmentId: string) => {
    setEditorState(prev => ({
      ...prev,
      segments: prev.segments.map(s => 
        s.id === segmentId ? { ...s, isEditing: false } : s
      )
    }))
  }, [])

  // Handle segment cancel
  const handleSegmentCancel = useCallback((segmentId: string) => {
    setEditorState(prev => {
      const originalSegment = prev.undoStack[prev.undoStack.length - 1]?.find(s => s.id === segmentId)
      if (originalSegment) {
        return {
          ...prev,
          segments: prev.segments.map(s => 
            s.id === segmentId 
              ? { ...originalSegment, isEditing: false }
              : s
          ),
          hasUnsavedChanges: prev.segments.some(s => s.id !== segmentId && s.hasChanges)
        }
      }
      return {
        ...prev,
        segments: prev.segments.map(s => 
          s.id === segmentId ? { ...s, isEditing: false } : s
        )
      }
    })
  }, [])

  // Apply AI suggestion
  const handleApplySuggestion = useCallback((segmentId: string, suggestionId: string) => {
    setEditorState(prev => {
      const segment = prev.segments.find(s => s.id === segmentId)
      const suggestion = segment?.aiSuggestions?.find(s => s.id === suggestionId)
      
      if (!segment || !suggestion) return prev
      
      const newContent = segment.content.replace(suggestion.original, suggestion.suggested)
      
      return {
        ...prev,
        segments: prev.segments.map(s => 
          s.id === segmentId 
            ? { 
                ...s, 
                content: newContent, 
                hasChanges: true,
                aiSuggestions: s.aiSuggestions?.filter(sug => sug.id !== suggestionId)
              }
            : s
        ),
        hasUnsavedChanges: true,
        undoStack: [...prev.undoStack.slice(-9), prev.segments]
      }
    })
  }, [])

  // Auto-save handler
  const handleAutoSave = useCallback(async () => {
    if (!editorState.hasUnsavedChanges) return
    
    setEditorState(prev => ({ ...prev, isAutoSaving: true }))
    
    try {
      // Simulate API call
      await new Promise(resolve => setTimeout(resolve, 500))
      
      setEditorState(prev => ({ 
        ...prev, 
        isAutoSaving: false, 
        hasUnsavedChanges: false,
        segments: prev.segments.map(s => ({ ...s, hasChanges: false }))
      }))
    } catch (error) {
      setEditorState(prev => ({ ...prev, isAutoSaving: false }))
    }
  }, [editorState.hasUnsavedChanges])

  // Manual save
  const handleSave = useCallback(() => {
    onSave?.(editorState.segments)
    setEditorState(prev => ({ 
      ...prev, 
      hasUnsavedChanges: false,
      segments: prev.segments.map(s => ({ ...s, hasChanges: false }))
    }))
  }, [editorState.segments, onSave])

  // Undo/Redo
  const handleUndo = useCallback(() => {
    setEditorState(prev => {
      if (prev.undoStack.length === 0) return prev
      
      const previousState = prev.undoStack[prev.undoStack.length - 1]
      return {
        ...prev,
        segments: previousState,
        undoStack: prev.undoStack.slice(0, -1),
        redoStack: [prev.segments, ...prev.redoStack.slice(0, 9)],
        hasUnsavedChanges: true
      }
    })
  }, [])

  const handleRedo = useCallback(() => {
    setEditorState(prev => {
      if (prev.redoStack.length === 0) return prev
      
      const nextState = prev.redoStack[0]
      return {
        ...prev,
        segments: nextState,
        redoStack: prev.redoStack.slice(1),
        undoStack: [...prev.undoStack.slice(-9), prev.segments],
        hasUnsavedChanges: true
      }
    })
  }, [])

  // Toggle preview mode
  const handleTogglePreview = useCallback(() => {
    setEditorState(prev => ({ ...prev, isPreviewMode: !prev.isPreviewMode }))
  }, [])

  // Refresh AI analysis
  const handleRefreshAI = useCallback(async () => {
    if (!enableAIPreview) return
    
    setAiProcessing(true)
    setEditorState(prev => ({ ...prev, aiPreviewProgress: 0 }))
    
    try {
      // Simulate AI processing with progress
      for (let i = 0; i <= 100; i += 10) {
        setEditorState(prev => ({ ...prev, aiPreviewProgress: i }))
        await new Promise(resolve => setTimeout(resolve, 100))
      }
      
      // Mock AI suggestions
      setEditorState(prev => ({
        ...prev,
        segments: prev.segments.map(segment => ({
          ...segment,
          aiSuggestions: segment.type !== 'metadata' ? [{
            id: `suggestion-${segment.id}`,
            type: 'clarity',
            original: 'can you',
            suggested: 'could you please',
            confidence: 0.85,
            reason: 'More polite phrasing'
          }] : undefined
        }))
      }))
    } catch (error) {
      console.error('AI processing failed:', error)
    } finally {
      setAiProcessing(false)
    }
  }, [enableAIPreview])

  // Export handler
  const handleExport = useCallback(() => {
    const exportData = {
      conversationId,
      segments: editorState.segments,
      exportedAt: new Date().toISOString()
    }
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `conversation-${conversationId}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [conversationId, editorState.segments])

  return (
    <div className={cn('h-full flex flex-col', className)}>
      {/* Toolbar */}
      <EditorToolbar
        hasUnsavedChanges={editorState.hasUnsavedChanges}
        canUndo={editorState.undoStack.length > 0}
        canRedo={editorState.redoStack.length > 0}
        isPreviewMode={editorState.isPreviewMode}
        onSave={handleSave}
        onUndo={handleUndo}
        onRedo={handleRedo}
        onTogglePreview={handleTogglePreview}
        onExport={handleExport}
        onAutoSaveToggle={setAutoSaveEnabled}
        autoSaveEnabled={autoSaveEnabled}
      />

      {/* Main Content */}
      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup direction="horizontal" className="h-full">
          {/* Original Content Panel */}
          <ResizablePanel defaultSize={30} minSize={20}>
            <div className="h-full flex flex-col">
              <div className="p-3 border-b bg-muted/30">
                <h3 className="font-medium text-sm flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Original Content
                </h3>
              </div>
              <ScrollArea className="flex-1 p-4">
                <pre className="whitespace-pre-wrap text-sm font-mono leading-relaxed">
                  {originalContent}
                </pre>
              </ScrollArea>
            </div>
          </ResizablePanel>

          <ResizableHandle />

          {/* Editor Panel */}
          <ResizablePanel defaultSize={70} minSize={40}>
            <div className="h-full flex flex-col">
              <ResizablePanelGroup direction="horizontal" className="h-full">
                {/* Segments Editor */}
                <ResizablePanel defaultSize={enableAIPreview ? 60 : 100} minSize={40}>
                  <div className="h-full flex flex-col">
                    <div className="p-3 border-b bg-muted/30">
                      <div className="flex items-center justify-between">
                        <h3 className="font-medium text-sm flex items-center gap-2">
                          <Edit3 className="h-4 w-4" />
                          Extracted Segments
                        </h3>
                        {editorState.isAutoSaving && (
                          <div className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Clock className="h-3 w-3 animate-spin" />
                            Auto-saving...
                          </div>
                        )}
                      </div>
                    </div>
                    <ScrollArea className="flex-1 p-4">
                      {editorState.segments.map((segment) => (
                        <SegmentComponent
                          key={segment.id}
                          segment={segment}
                          isSelected={editorState.selectedSegmentId === segment.id}
                          isEditing={segment.isEditing || false}
                          onSelect={handleSegmentSelect}
                          onEdit={handleSegmentEdit}
                          onSave={handleSegmentSave}
                          onCancel={handleSegmentCancel}
                          onApplySuggestion={handleApplySuggestion}
                        />
                      ))}
                    </ScrollArea>
                  </div>
                </ResizablePanel>

                {/* AI Preview Panel */}
                {enableAIPreview && (
                  <>
                    <ResizableHandle />
                    <ResizablePanel defaultSize={40} minSize={25}>
                      <div className="h-full flex flex-col">
                        <div className="p-3 border-b bg-muted/30">
                          <h3 className="font-medium text-sm flex items-center gap-2">
                            <Bot className="h-4 w-4" />
                            AI Preview
                          </h3>
                        </div>
                        <ScrollArea className="flex-1 p-4">
                          <AIPreviewPanel
                            segments={editorState.segments}
                            isLoading={aiProcessing}
                            progress={editorState.aiPreviewProgress}
                            onRefresh={handleRefreshAI}
                          />
                        </ScrollArea>
                      </div>
                    </ResizablePanel>
                  </>
                )}
              </ResizablePanelGroup>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {/* Status Bar */}
      <div className="flex items-center justify-between p-2 border-t text-xs text-muted-foreground bg-muted/30">
        <div className="flex items-center gap-4">
          <span>{editorState.segments.length} segments</span>
          <span>
            {editorState.segments.filter(s => s.validationStatus === 'valid').length} valid
          </span>
          {editorState.hasUnsavedChanges && (
            <span className="text-yellow-600">Unsaved changes</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {editorState.selectedSegmentId && (
            <span>Selected: {editorState.selectedSegmentId}</span>
          )}
        </div>
      </div>
    </div>
  )
}

export default ConversationEditor