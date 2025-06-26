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
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog'
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
  type ConversationVersion,
  type VersionListResponse,
  type ConversationEditRequest,
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
  const [errors, setErrors] = useState<FormErrors>({})
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

  // Load version history on mount
  useEffect(() => {
    if (isOpen) {
      loadVersionHistory()
    }
  }, [isOpen, conversation.id])

  // Track unsaved changes
  useEffect(() => {
    const hasChanges = 
      formData.title !== conversation.title ||
      formData.transcript !== (conversation.metadata?.raw_transcript || '')
    
    setHasUnsavedChanges(hasChanges)
  }, [formData, conversation])

  const loadVersionHistory = async () => {
    try {
      setIsLoadingVersions(true)
      const response = await getConversationVersions(conversation.id)
      setVersions(response.versions)
    } catch (error) {
      console.error('Failed to load version history:', error)
      toast({
        title: 'Error',
        description: 'Failed to load version history',
        variant: 'destructive'
      })
    } finally {
      setIsLoadingVersions(false)
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
    if (!validateForm()) {
      return
    }

    try {
      setIsSaving(true)

      const editRequest: ConversationEditRequest = {
        title: formData.title.trim(),
        raw_transcript: formData.transcript.trim(),
        updated_by: currentUser,
        reprocess: reprocessAfterSave
      }

      const response: EditResponse = await editConversation(conversation.id, editRequest)

      // Update conversation data
      if (onConversationUpdated) {
        onConversationUpdated(response.conversation)
      }

      // Reload version history
      await loadVersionHistory()

      // Show success message
      toast({
        title: 'Success',
        description: `Conversation updated to version ${response.new_version}${
          response.reprocessing ? ' and scheduled for reprocessing' : ''
        }`
      })

      // Show reprocess status if applicable
      if (response.reprocessing && response.task_id) {
        setShowReprocessOption(true)
      }

      // Reset unsaved changes flag
      setHasUnsavedChanges(false)

      // Close modal
      onClose()

    } catch (error) {
      console.error('Failed to save conversation:', error)
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to save conversation',
        variant: 'destructive'
      })
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
    try {
      setIsLoading(true)

      const response = await revertConversation(conversation.id, versionNumber, {
        target_version: versionNumber,
        reverted_by: currentUser,
        reason: 'Manual revert via UI',
        reprocess: true
      })

      // Update form data with reverted content
      const revertedVersion = versions.find(v => v.version === versionNumber)
      if (revertedVersion) {
        setFormData({
          title: revertedVersion.title,
          transcript: revertedVersion.raw_transcript
        })
      }

      // Reload version history
      await loadVersionHistory()

      toast({
        title: 'Success',
        description: `Reverted to version ${versionNumber}, created version ${response.new_version}`
      })

      setActiveTab('edit')

    } catch (error) {
      console.error('Failed to revert conversation:', error)
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to revert conversation',
        variant: 'destructive'
      })
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
        </DialogHeader>

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
                <Label htmlFor="transcript">Transcript Content</Label>
                <div className="flex-1 overflow-hidden">
                  <RichTextEditor
                    value={formData.transcript}
                    onChange={(value) => setFormData(prev => ({ ...prev, transcript: value }))}
                    placeholder="Enter transcript content..."
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