/**
 * Unified Text Canvas for FeedMe System
 * Replaces fragmented Q&A sections with a single editable text area
 * 
 * Features:
 * - Display extracted text in a unified canvas
 * - Edit text with real-time preview
 * - Processing method indicators (PDF OCR, manual entry, etc.)
 * - Confidence scoring and quality indicators
 * - Approval workflow integration
 * - Text statistics and metadata
 */

'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { 
  Edit3, 
  Save, 
  X, 
  FileText, 
  Eye, 
  Zap, 
  AlertTriangle,
  CheckCircle2,
  Info,
  Clock,
  User,
  Bot,
  Sparkles
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDistanceToNow } from 'date-fns'

// Types
interface ProcessingMetadata {
  processing_method: 'pdf_ocr' | 'manual_text' | 'text_paste'
  extraction_confidence?: number
  processing_time_ms?: number
  quality_metrics?: Record<string, number>
  extraction_method?: string
  warnings?: string[]
}

interface TextStatistics {
  character_count: number
  word_count: number
  line_count: number
  paragraph_count: number
  estimated_read_time_minutes: number
}

interface UnifiedTextCanvasProps {
  conversationId: number
  title: string
  extractedText: string
  processingMetadata: ProcessingMetadata
  approvalStatus: 'pending' | 'approved' | 'rejected'
  approvedBy?: string
  approvedAt?: string
  pdfCleaned?: boolean
  pdfCleanedAt?: string
  originalPdfSize?: number
  onTextUpdate?: (text: string) => Promise<void>
  onApprovalAction?: (action: 'approve' | 'reject' | 'edit_and_approve', data?: any) => Promise<void>
  readOnly?: boolean
  showApprovalControls?: boolean
  fullPageMode?: boolean
}

export function UnifiedTextCanvas({
  conversationId,
  title,
  extractedText,
  processingMetadata,
  approvalStatus,
  approvedBy,
  approvedAt,
  pdfCleaned = false,
  pdfCleanedAt,
  originalPdfSize,
  onTextUpdate,
  onApprovalAction,
  readOnly = false,
  showApprovalControls = false,
  fullPageMode = false
}: UnifiedTextCanvasProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editedText, setEditedText] = useState(extractedText)
  const [isLoading, setIsLoading] = useState(false)
  const [textStats, setTextStats] = useState<TextStatistics | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Calculate text statistics
  const calculateTextStats = useCallback((text: string): TextStatistics => {
    const lines = text.split('\n')
    const paragraphs = text.split('\n\n').filter(p => p.trim().length > 0)
    const words = text.trim().split(/\s+/).filter(w => w.length > 0)
    
    return {
      character_count: text.length,
      word_count: words.length,
      line_count: lines.length,
      paragraph_count: paragraphs.length,
      estimated_read_time_minutes: Math.max(1, Math.ceil(words.length / 200))
    }
  }, [])

  // Update text statistics when text changes
  useEffect(() => {
    if (extractedText) {
      setTextStats(calculateTextStats(extractedText))
    }
  }, [extractedText, calculateTextStats])

  // Update edited text when extracted text changes
  useEffect(() => {
    setEditedText(extractedText)
  }, [extractedText])

  // Handle saving edited text
  const handleSaveText = async () => {
    if (!onTextUpdate || editedText === extractedText) {
      setIsEditing(false)
      return
    }

    setIsLoading(true)
    try {
      await onTextUpdate(editedText)
      setIsEditing(false)
    } catch (error) {
      console.error('Failed to save text:', error)
      // Reset to original text on error
      setEditedText(extractedText)
    } finally {
      setIsLoading(false)
    }
  }

  // Handle canceling edit
  const handleCancelEdit = () => {
    setEditedText(extractedText)
    setIsEditing(false)
  }

  // Handle approval actions
  const handleApprovalAction = async (action: 'approve' | 'reject' | 'edit_and_approve') => {
    if (!onApprovalAction) return

    setIsLoading(true)
    try {
      const data = action === 'edit_and_approve' ? { edited_text: editedText } : undefined
      await onApprovalAction(action, data)
      if (action === 'edit_and_approve') {
        setIsEditing(false)
      }
    } catch (error) {
      console.error('Failed to process approval action:', error)
    } finally {
      setIsLoading(false)
    }
  }

  // Get processing method display info
  const getProcessingMethodInfo = () => {
    const { processing_method, extraction_confidence, extraction_method } = processingMetadata
    
    const methodInfo = {
      pdf_ocr: {
        label: 'PDF OCR',
        icon: <Bot className="h-4 w-4" />,
        color: 'bg-blue-100 text-blue-700',
        description: 'Text extracted using OCR technology'
      },
      manual_text: {
        label: 'Manual Entry',
        icon: <User className="h-4 w-4" />,
        color: 'bg-green-100 text-green-700',
        description: 'Manually entered text'
      },
      text_paste: {
        label: 'Text Paste',
        icon: <FileText className="h-4 w-4" />,
        color: 'bg-purple-100 text-purple-700',
        description: 'Pasted text content'
      }
    }

    const info = methodInfo[processing_method] || methodInfo.manual_text
    
    return {
      ...info,
      confidence: extraction_confidence,
      enhanced: extraction_method === 'ocr_fallback'
    }
  }

  // Get confidence indicator
  const getConfidenceIndicator = (confidence?: number) => {
    if (confidence === undefined) return null

    if (confidence >= 0.9) {
      return <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
        <CheckCircle2 className="h-3 w-3 mr-1" />
        High Confidence ({Math.round(confidence * 100)}%)
      </Badge>
    } else if (confidence >= 0.7) {
      return <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">
        <AlertTriangle className="h-3 w-3 mr-1" />
        Medium Confidence ({Math.round(confidence * 100)}%)
      </Badge>
    } else {
      return <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">
        <AlertTriangle className="h-3 w-3 mr-1" />
        Low Confidence ({Math.round(confidence * 100)}%)
      </Badge>
    }
  }

  // Get approval status indicator
  const getApprovalStatusIndicator = () => {
    switch (approvalStatus) {
      case 'approved':
        return <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
          <CheckCircle2 className="h-3 w-3 mr-1" />
          Approved
        </Badge>
      case 'rejected':
        return <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">
          <X className="h-3 w-3 mr-1" />
          Rejected
        </Badge>
      default:
        return <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">
          <Clock className="h-3 w-3 mr-1" />
          Pending Review
        </Badge>
    }
  }

  const methodInfo = getProcessingMethodInfo()

  return (
    <div className="space-y-6">
      {/* Header with metadata */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="text-lg">{title}</CardTitle>
              <div className="flex items-center gap-4 mt-2">
                <Badge variant="outline" className={cn("text-sm", methodInfo.color)}>
                  {methodInfo.icon}
                  <span className="ml-1">{methodInfo.label}</span>
                  {methodInfo.enhanced && <Sparkles className="h-3 w-3 ml-1" />}
                </Badge>
                {getConfidenceIndicator(methodInfo.confidence)}
                {getApprovalStatusIndicator()}
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              {!readOnly && (
                <>
                  {isEditing ? (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCancelEdit}
                        disabled={isLoading}
                      >
                        <X className="h-4 w-4 mr-1" />
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSaveText}
                        disabled={isLoading || editedText === extractedText}
                      >
                        <Save className="h-4 w-4 mr-1" />
                        Save
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setIsEditing(true)}
                      disabled={isLoading}
                    >
                      <Edit3 className="h-4 w-4 mr-1" />
                      Edit
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Processing warnings */}
          {processingMetadata.warnings && processingMetadata.warnings.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
              <div className="flex items-start gap-2">
                <Info className="h-4 w-4 text-yellow-600 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-yellow-800">Processing Notes</p>
                  <ul className="text-sm text-yellow-700 mt-1 space-y-1">
                    {processingMetadata.warnings.map((warning, index) => (
                      <li key={index}>• {warning}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* Text statistics */}
          {textStats && (
            <div className="flex items-center gap-6 text-sm text-muted-foreground">
              <span>{textStats.word_count.toLocaleString()} words</span>
              <span>{textStats.character_count.toLocaleString()} characters</span>
              <span>{textStats.paragraph_count} paragraphs</span>
              <span>~{textStats.estimated_read_time_minutes} min read</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Main content area */}
      <Tabs defaultValue="text" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="text" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Text Content
          </TabsTrigger>
          <TabsTrigger value="metadata" className="flex items-center gap-2">
            <Info className="h-4 w-4" />
            Metadata
          </TabsTrigger>
        </TabsList>

        <TabsContent value="text" className="space-y-4">
          <Card className={cn(fullPageMode && "border-0 shadow-none")}>
            <CardContent className="p-0">
              {isEditing ? (
                <div className={cn(
                  "relative",
                  fullPageMode && "min-h-[calc(100vh-300px)]"
                )}>
                  <Textarea
                    ref={textareaRef}
                    value={editedText}
                    onChange={(e) => setEditedText(e.target.value)}
                    placeholder="Enter extracted text..."
                    className={cn(
                      "border-0 resize-none focus:ring-0 font-mono text-sm",
                      fullPageMode ? "min-h-[calc(100vh-300px)] p-6" : "min-h-[400px] p-4"
                    )}
                    disabled={isLoading}
                  />
                  {/* Character count in edit mode */}
                  <div className="absolute bottom-4 right-4 text-xs text-muted-foreground bg-background px-2 py-1 rounded">
                    {editedText.length.toLocaleString()} characters
                  </div>
                </div>
              ) : (
                <ScrollArea className={cn(
                  fullPageMode ? "h-[calc(100vh-300px)]" : "h-[400px]"
                )}>
                  <div className={cn(
                    "whitespace-pre-wrap font-mono text-sm leading-relaxed",
                    fullPageMode ? "p-6" : "p-4"
                  )}>
                    {extractedText || (
                      <div className="text-muted-foreground italic">
                        No text content available
                      </div>
                    )}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          {/* Approval controls */}
          {showApprovalControls && approvalStatus === 'pending' && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Approval Actions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <Button
                    variant="outline"
                    onClick={() => handleApprovalAction('approve')}
                    disabled={isLoading}
                    className="text-green-700 border-green-300 hover:bg-green-50"
                  >
                    <CheckCircle2 className="h-4 w-4 mr-1" />
                    Approve
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => handleApprovalAction('reject')}
                    disabled={isLoading}
                    className="text-red-700 border-red-300 hover:bg-red-50"
                  >
                    <X className="h-4 w-4 mr-1" />
                    Reject
                  </Button>
                  {isEditing && (
                    <Button
                      onClick={() => handleApprovalAction('edit_and_approve')}
                      disabled={isLoading || editedText === extractedText}
                      className="text-blue-700 bg-blue-50 border-blue-300 hover:bg-blue-100"
                    >
                      <Edit3 className="h-4 w-4 mr-1" />
                      Edit & Approve
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Approval history */}
          {approvalStatus === 'approved' && approvedBy && (
            <Card>
              <CardContent className="pt-4 space-y-2">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="h-4 w-4 text-green-600" />
                  <span>Approved by {approvedBy}</span>
                  {approvedAt && (
                    <span>• {formatDistanceToNow(new Date(approvedAt), { addSuffix: true })}</span>
                  )}
                </div>
                
                {/* PDF cleanup status */}
                {processingMetadata.processing_method === 'pdf_ocr' && (
                  <div className="flex items-center gap-2 text-sm">
                    {pdfCleaned ? (
                      <>
                        <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          PDF Cleaned
                        </Badge>
                        {originalPdfSize && (
                          <span className="text-muted-foreground">
                            • Saved {(originalPdfSize / 1024 / 1024).toFixed(2)} MB
                          </span>
                        )}
                        {pdfCleanedAt && (
                          <span className="text-muted-foreground">
                            • {formatDistanceToNow(new Date(pdfCleanedAt), { addSuffix: true })}
                          </span>
                        )}
                      </>
                    ) : (
                      <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-300">
                        <Clock className="h-3 w-3 mr-1" />
                        PDF Cleanup Pending
                      </Badge>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="metadata" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Processing Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="font-medium">Method:</span>
                  <span className="ml-2">{methodInfo.label}</span>
                </div>
                {methodInfo.confidence !== undefined && (
                  <div>
                    <span className="font-medium">Confidence:</span>
                    <span className="ml-2">{Math.round(methodInfo.confidence * 100)}%</span>
                  </div>
                )}
                {processingMetadata.processing_time_ms && (
                  <div>
                    <span className="font-medium">Processing Time:</span>
                    <span className="ml-2">{processingMetadata.processing_time_ms}ms</span>
                  </div>
                )}
                <div>
                  <span className="font-medium">Conversation ID:</span>
                  <span className="ml-2">{conversationId}</span>
                </div>
              </div>

              {processingMetadata.quality_metrics && (
                <>
                  <Separator />
                  <div>
                    <h4 className="font-medium mb-2">Quality Metrics</h4>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      {Object.entries(processingMetadata.quality_metrics).map(([key, value]) => (
                        <div key={key}>
                          <span className="font-medium capitalize">{key.replace('_', ' ')}:</span>
                          <span className="ml-2">
                            {typeof value === 'number' ? 
                              (value < 1 ? `${Math.round(value * 100)}%` : value.toLocaleString()) 
                              : String(value)
                            }
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default UnifiedTextCanvas