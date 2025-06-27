/**
 * FeedMe v2.0 Phase 3: Edit Conversation Modal
 * Rich text editor with version control for transcript editing
 * 
 * Features:
 * - Rich text editor with formatting toolbar
 * - Version history panel with diff visualization
 * - Save and reprocess workflow
 * - Validation and error handling
 * - Real-time preview
 */

'use client'

import React, { useState, useEffect, useRef } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs'
import { Alert, AlertDescription } from '../ui/alert'
import { Badge } from '../ui/badge'
import { Loader2, Save, RotateCcw, History, Eye, Edit3 } from 'lucide-react'
import { cn } from '../../lib/utils'
import { toast } from '../ui/use-toast'
import {
  editConversation,
  getConversationVersions,
  revertConversation,
  getFormattedQAContent,
  type ConversationVersion,
  type VersionListResponse,
  type ConversationEditRequest,
  type ConversationRevertRequest,
  type EditResponse,
  type UploadTranscriptResponse
} from '../../lib/feedme-api'
import { VersionHistoryPanel } from './VersionHistoryPanel'
import { DiffViewer } from './DiffViewer'
import { RichTextEditor } from './RichTextEditor'

interface EditConversationModalProps {
  isOpen: boolean
  onClose: () => void
  conversation: UploadTranscriptResponse
  onConversationUpdated?: (conversation: UploadTranscriptResponse) => void
}

interface FormData {
  title: string
  transcript: string
}

interface ContentData {
  formatted_content: string
  total_examples: number
  content_type: 'qa_examples' | 'raw_transcript'
  raw_transcript?: string
  message: string
}

interface FormErrors {
  title?: string
  transcript?: string
}

export function EditConversationModal({
  isOpen,
  onClose,
  conversation,
  onConversationUpdated
}: EditConversationModalProps) {
  // Form state
  const [formData, setFormData] = useState<FormData>({
    title: conversation.title,
    transcript: conversation.metadata?.raw_transcript || ''
  })
  const [contentData, setContentData] = useState<ContentData | null>(null)
  const [isLoadingContent, setIsLoadingContent] = useState(false)
  const [errors, setErrors] = useState<FormErrors>({})
  const [apiError, setApiError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  
  // Version management state
  const [versions, setVersions] = useState<ConversationVersion[]>([])
  const [isLoadingVersions, setIsLoadingVersions] = useState(false)
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null)
  const [showDiff, setShowDiff] = useState(false)
  
  // UI state
  const [activeTab, setActiveTab] = useState<'edit' | 'history' | 'diff'>('edit')
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [showReprocessOption, setShowReprocessOption] = useState(false)
  const [reprocessAfterSave, setReprocessAfterSave] = useState(true)
  
  // Current user (mock for now - would come from auth context)
  const currentUser = 'editor@example.com'

  // Load version history and formatted content on mount
  useEffect(() => {
    if (isOpen) {
      loadVersionHistory()
      loadFormattedContent()
    }
  }, [isOpen, conversation.id])

  // Track unsaved changes
  useEffect(() => {
    const originalTranscript = contentData?.formatted_content || conversation.metadata?.raw_transcript || ''
    const hasChanges = 
      formData.title !== conversation.title ||
      formData.transcript !== originalTranscript
    
    setHasUnsavedChanges(hasChanges)
  }, [formData, conversation, contentData])

  const loadVersionHistory = async () => {
    setApiError(null)
    try {
      setIsLoadingVersions(true)
      const response = await getConversationVersions(conversation.id)
      setVersions(response.versions)
    } catch (error) {
      console.error('Failed to load version history:', error)
      // Don't show error for pending conversations (versions may not exist yet)
      if (conversation.processing_status !== 'pending') {
        const message = error instanceof Error ? error.message : 'Could not load version history.'
        setApiError(message)
      }
      // Set empty versions array for pending conversations
      setVersions([])
    } finally {
      setIsLoadingVersions(false)
    }
  }

  const loadFormattedContent = async () => {
    setApiError(null)
    try {
      setIsLoadingContent(true)
      const content = await getFormattedQAContent(conversation.id)
      setContentData(content)
      
      // Update the form with the formatted content
      setFormData(prev => ({
        ...prev,
        transcript: content.formatted_content
      }))
      
      console.log(`[EditModal] Loaded ${content.content_type}: ${content.message}`)
    } catch (error) {
      console.error('Failed to load formatted content:', error)
      // Keep the existing raw transcript on error
      const fallbackContent = conversation.metadata?.raw_transcript || ''
      setFormData(prev => ({
        ...prev,
        transcript: fallbackContent
      }))
      
      // Don't show error for this - just log it
      console.log('[EditModal] Using raw transcript as fallback')
    } finally {
      setIsLoadingContent(false)
    }
  }

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {}

    if (!formData.title.trim()) {
      newErrors.title = 'Title is required'
    }

    if (!formData.transcript.trim()) {
      newErrors.transcript = 'Transcript content cannot be empty'
    }

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSave = async () => {
    setApiError(null)
    if (!validateForm()) {
      return
    }

    setIsSaving(true)
    try {
      const payload: ConversationEditRequest = {
        title: formData.title,
        raw_transcript: formData.transcript,
        reprocess: reprocessAfterSave,
        updated_by: currentUser
      }

      const response = await editConversation(conversation.id, payload)

      toast({
        title: 'Success',
        description: `Saved as v${response.new_version}.${response.reprocessing ? ' Reprocessing...' : ''}`
      })

      if (onConversationUpdated) {
        onConversationUpdated(response.conversation)
      }
      handleClose()
    } catch (error) {
      console.error('Save failed:', error)
      const message = error instanceof Error ? error.message : 'An unknown error occurred.'
      setApiError(`Failed to save changes: ${message}`)
    } finally {
      setIsSaving(false)
    }
  }

  const handleVersionSelect = (versionNumber: number) => {
    setSelectedVersion(versionNumber)
    setShowDiff(true)
    setActiveTab('diff')
  }

  const handleRevert = async (versionNumber: number) => {
    setApiError(null)
    setIsLoading(true)
    try {
      const revertPayload: ConversationRevertRequest = {
        target_version: versionNumber,
        reverted_by: currentUser,
        reason: 'Manual revert from UI',
        reprocess: true
      }
      const response = await revertConversation(conversation.id, versionNumber, revertPayload)

      toast({
        title: 'Success',
        description: `Reverted to v${response.reverted_to_version}. New active version is v${response.new_version}.`
      })

      // Update form data with reverted content
      setFormData({
        title: response.conversation.title,
        transcript: response.conversation.metadata?.raw_transcript || ''
      })

      // Refresh version history to show new active version
      await loadVersionHistory()

      // Notify parent component
      if (onConversationUpdated) {
        onConversationUpdated(response.conversation)
      }

      // Switch back to edit tab
      setActiveTab('edit')
    } catch (error) {
      console.error(`Failed to revert to version ${versionNumber}:`, error)
      const message = error instanceof Error ? error.message : 'An unknown error occurred.'
      setApiError(`Failed to revert to version ${versionNumber}: ${message}`)
    } finally {
      setIsLoading(false)
    }
  }

  const handleClose = () => {
    if (hasUnsavedChanges) {
      const confirmed = window.confirm(
        'You have unsaved changes. Are you sure you want to close without saving?'
      )
      if (!confirmed) return
    }
    onClose()
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Edit3 className="h-5 w-5" />
            Edit Conversation
            {hasUnsavedChanges && <Badge variant="outline">Unsaved Changes</Badge>}
          </DialogTitle>
          <DialogDescription>
            Edit the conversation title and transcript. You can view version history, see diffs, and revert to previous versions.
          </DialogDescription>
        </DialogHeader>

        {apiError && (
          <Alert variant="destructive" className="my-4">
            <AlertDescription>{apiError}</AlertDescription>
          </Alert>
        )}

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)} className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="edit" className="flex items-center gap-2">
              <Edit3 className="h-4 w-4" />
              Edit
            </TabsTrigger>
            <TabsTrigger value="history" className="flex items-center gap-2">
              <History className="h-4 w-4" />
              Version History
              {versions.length > 1 && (
                <Badge variant="secondary" className="ml-1">
                  {versions.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="diff" disabled={!showDiff} className="flex items-center gap-2">
              <Eye className="h-4 w-4" />
              Compare
            </TabsTrigger>
          </TabsList>

          {/* Edit Tab */}
          <TabsContent value="edit" className="flex-1 flex flex-col overflow-hidden mt-4">
            <div className="flex flex-col gap-4 flex-1 overflow-hidden">
              {/* Title Input */}
              <div className="space-y-2">
                <Label htmlFor="title">Title</Label>
                <Input
                  id="title"
                  value={formData.title}
                  onChange={(e) => setFormData(prev => ({ ...prev, title: e.target.value }))}
                  className={cn(errors.title && 'border-red-500')}
                  placeholder="Enter conversation title..."
                />
                {errors.title && (
                  <p className="text-sm text-red-500">{errors.title}</p>
                )}
              </div>

              {/* Rich Text Editor */}
              <div className="space-y-2 flex-1 flex flex-col overflow-hidden">
                <div className="flex items-center justify-between">
                  <Label htmlFor="transcript">
                    {contentData?.content_type === 'qa_examples' ? 'Q&A Examples' : 'Transcript Content'}
                  </Label>
                  {isLoadingContent && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Loading content...
                    </div>
                  )}
                  {contentData && (
                    <Badge variant={contentData.content_type === 'qa_examples' ? 'default' : 'secondary'}>
                      {contentData.content_type === 'qa_examples' 
                        ? `${contentData.total_examples} Examples` 
                        : 'Raw Transcript'}
                    </Badge>
                  )}
                </div>
                {contentData?.message && (
                  <p className="text-xs text-muted-foreground">{contentData.message}</p>
                )}
                <div className="flex-1 overflow-hidden">
                  <RichTextEditor
                    value={formData.transcript}
                    onChange={(value) => setFormData(prev => ({ ...prev, transcript: value }))}
                    placeholder={
                      contentData?.content_type === 'qa_examples' 
                        ? "Edit Q&A examples (markdown format)..."
                        : "Enter transcript content..."
                    }
                    className={cn(
                      'h-full',
                      errors.transcript && 'border-red-500'
                    )}
                  />
                </div>
                {errors.transcript && (
                  <p className="text-sm text-red-500">{errors.transcript}</p>
                )}
              </div>

              {/* Reprocess Option */}
              {hasUnsavedChanges && (
                <Alert>
                  <AlertDescription className="flex items-center justify-between">
                    <span>Reprocess transcript after saving to extract new Q&A examples?</span>
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="reprocess"
                        checked={reprocessAfterSave}
                        onChange={(e) => setReprocessAfterSave(e.target.checked)}
                        className="rounded"
                      />
                      <Label htmlFor="reprocess" className="text-sm">
                        Auto-reprocess
                      </Label>
                    </div>
                  </AlertDescription>
                </Alert>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex justify-end gap-2 pt-4 border-t">
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button 
                onClick={handleSave} 
                disabled={isSaving || !hasUnsavedChanges}
                className="flex items-center gap-2"
              >
                {isSaving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {isSaving ? 'Saving...' : 'Save Changes'}
              </Button>
            </div>
          </TabsContent>

          {/* Version History Tab */}
          <TabsContent value="history" className="flex-1 overflow-hidden mt-4">
            <VersionHistoryPanel
              conversationId={conversation.id}
              versions={versions}
              isLoading={isLoadingVersions}
              onSelectVersion={handleVersionSelect}
              onRevertVersion={handleRevert}
              onRefresh={loadVersionHistory}
            />
          </TabsContent>

          {/* Diff Viewer Tab */}
          <TabsContent value="diff" className="flex-1 overflow-hidden mt-4">
            {showDiff && selectedVersion && (
              <DiffViewer
                conversationId={conversation.id}
                fromVersion={selectedVersion}
                toVersion={versions.find(v => v.is_active)?.version || 1}
                onClose={() => {
                  setShowDiff(false)
                  setSelectedVersion(null)
                  setActiveTab('history')
                }}
              />
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}