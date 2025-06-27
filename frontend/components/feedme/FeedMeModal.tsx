"use client"

import React, { useState, useCallback } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Upload, FileText, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import { uploadTranscriptFile, uploadTranscriptText, getProcessingStatus } from '@/lib/feedme-api'

interface FeedMeModalProps {
  isOpen: boolean
  onClose: () => void
}

interface UploadState {
  isUploading: boolean
  progress: number
  error: string | null
  success: boolean
  conversationId?: number
  processingStatus?: string
}

interface FilePreview {
  isHtml: boolean
  messageCount?: number
  attachmentCount?: number
  description?: string
}

export function FeedMeModal({ isOpen, onClose }: FeedMeModalProps) {
  const [title, setTitle] = useState('')
  const [textContent, setTextContent] = useState('')
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
  const [activeTab, setActiveTab] = useState('file')
  const [isDragActive, setIsDragActive] = useState(false)
  const [filePreview, setFilePreview] = useState<FilePreview | null>(null)
  const [uploadState, setUploadState] = useState<UploadState>({
    isUploading: false,
    progress: 0,
    error: null,
    success: false
  })

  const userId = process.env.NEXT_PUBLIC_FEEDME_USER_ID || 'web-user'

  // File validation helper
  const validateFile = (file: File) => {
    // Validate file type (text files and HTML)
    const allowedTypes = ['text/plain', 'text/html', 'application/html', 'text/csv']
    const allowedExtensions = ['.txt', '.log', '.html', '.htm', '.csv']
    
    const hasValidType = file.type === '' || allowedTypes.includes(file.type) || file.type.startsWith('text/')
    const hasValidExtension = allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext))
    
    if (!hasValidType && !hasValidExtension) {
      setUploadState(prev => ({
        ...prev,
        error: 'Please upload a text or HTML file (.txt, .log, .html, .htm, or plain text)'
      }))
      return false
    }

    // Validate file size (10MB limit as per settings)
    const maxSize = 10 * 1024 * 1024 // 10MB
    if (file.size > maxSize) {
      setUploadState(prev => ({
        ...prev,
        error: 'File size must be less than 10MB'
      }))
      return false
    }

    return true
  }

  // HTML file analysis helper
  const analyzeHtmlFile = async (file: File): Promise<FilePreview> => {
    try {
      const content = await file.text()
      const parser = new DOMParser()
      const doc = parser.parseFromString(content, 'text/html')
      
      // Check if it's a Zendesk ticket
      const zendeskSelectors = [
        '.zd-comment',
        '[data-test-id="ticket-title"]',
        '[data-creator-name]',
        'meta[name="generator"][content*="Zendesk"]',
        '#zendesk',
        '.zendesk'
      ]
      const hasZendeskMarker = zendeskSelectors.some(sel => doc.querySelector(sel))
      const isZendeskTicket = hasZendeskMarker || /zendesk|zd-comment/i.test(content)
      
      if (isZendeskTicket) {
        // Count zd-comment divs (support messages)
        const commentDivs = doc.querySelectorAll('div.zd-comment, .zd-comment')
        
        // Count potential attachment links/references
        const attachmentLinks = doc.querySelectorAll('a[href*="attachment"], a[href*="download"], img')
        
        // Look for main email body content
        const mainBody = doc.querySelector('#html')
        const hasMainContent = mainBody && mainBody.textContent && mainBody.textContent.trim().length > 50
        
        const messageCount = commentDivs.length + (hasMainContent ? 1 : 0)
        
        return {
          isHtml: true,
          messageCount,
          attachmentCount: attachmentLinks.length,
          description: `Zendesk ticket detected – ${messageCount} message${messageCount !== 1 ? 's' : ''}, ${attachmentLinks.length} attachment${attachmentLinks.length !== 1 ? 's' : ''}`
        }
      } else {
        // Generic HTML file
        const textLength = doc.body?.textContent?.length || 0
        return {
          isHtml: true,
          description: `HTML file detected – ${Math.round(textLength / 100)} content blocks`
        }
      }
    } catch (error) {
      console.warn('Error analyzing HTML file:', error)
      return {
        isHtml: true,
        description: 'HTML file detected'
      }
    }
  }

  // Handle file selection
  const handleFileSelect = async (file: File) => {
    if (validateFile(file)) {
      setUploadedFile(file)
      setUploadState(prev => ({ ...prev, error: null }))
      
      // Auto-generate title from filename if not set
      if (!title.trim()) {
        const fileName = file.name.replace(/\.(txt|log|html|htm)$/i, '')
        setTitle(fileName)
      }

      // Analyze HTML files for preview
      const isHtmlFile = file.name.toLowerCase().endsWith('.html') || 
                        file.name.toLowerCase().endsWith('.htm') ||
                        file.type.includes('html')
      
      if (isHtmlFile) {
        try {
          const preview = await analyzeHtmlFile(file)
          setFilePreview(preview)
        } catch (error) {
          console.warn('Error analyzing HTML file:', error)
          setFilePreview({
            isHtml: true,
            description: 'HTML file detected'
          })
        }
      } else {
        setFilePreview(null)
      }
    }
  }

  // Native drag and drop handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragActive(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragActive(false)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragActive(false)

    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) {
      handleFileSelect(files[0])
    }
  }

  // Handle file input change
  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      handleFileSelect(files[0])
    }
  }

  // Reset form
  const resetForm = () => {
    setTitle('')
    setTextContent('')
    setUploadedFile(null)
    setFilePreview(null)
    setActiveTab('file')
    setUploadState({
      isUploading: false,
      progress: 0,
      error: null,
      success: false
    })
  }

  // Handle modal close
  const handleClose = () => {
    if (!uploadState.isUploading) {
      resetForm()
      onClose()
    }
  }

  // Form validation
  const isValid = () => {
    if (!title.trim()) return false
    if (activeTab === 'file' && !uploadedFile) return false
    if (activeTab === 'text' && !textContent.trim()) return false
    return true
  }

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!isValid()) {
      setUploadState(prev => ({
        ...prev,
        error: 'Please fill in all required fields'
      }))
      return
    }

    setUploadState({
      isUploading: true,
      progress: 20,
      error: null,
      success: false
    })

    try {
      let uploadResponse

      if (activeTab === 'file' && uploadedFile) {
        // Upload file
        setUploadState(prev => ({ ...prev, progress: 40 }))
        uploadResponse = await uploadTranscriptFile(title, uploadedFile, userId, true)
      } else if (activeTab === 'text' && textContent) {
        // Upload text content
        setUploadState(prev => ({ ...prev, progress: 40 }))
        uploadResponse = await uploadTranscriptText(title, textContent, userId, true)
      } else {
        throw new Error('Invalid upload data')
      }

      setUploadState(prev => ({ 
        ...prev, 
        progress: 60,
        conversationId: uploadResponse.id,
        processingStatus: uploadResponse.processing_status
      }))

      // Poll for processing completion with exponential backoff
      setUploadState(prev => ({ ...prev, progress: 80 }))
      let delay = 1000
      let statusResponse: any = null
      while (true) {
        try {
          statusResponse = await getProcessingStatus(uploadResponse.id)
          setUploadState(prev => ({
            ...prev,
            processingStatus: statusResponse.status
          }))
          if (statusResponse.status !== 'processing') {
            break
          }
        } catch (statusError) {
          console.warn('Status check failed:', statusError)
          break
        }
        await new Promise(resolve => setTimeout(resolve, delay))
        delay = Math.min(delay * 2, 10000)
      }

      setUploadState(prev => ({
        ...prev,
        progress: 100,
        processingStatus: statusResponse?.status || prev.processingStatus
      }))

      setUploadState(prev => ({
        ...prev,
        isUploading: false,
        success: true
      }))

      // Auto-close after success
      setTimeout(() => {
        handleClose()
      }, 3000)

    } catch (error) {
      console.error('Upload failed:', error)
      setUploadState({
        isUploading: false,
        progress: 0,
        error: error instanceof Error ? error.message : 'Upload failed. Please try again.',
        success: false
      })
    }
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open && !uploadState.isUploading) {
          handleClose()
        }
      }}
    >
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-accent">
            <Upload className="h-5 w-5" />
            FeedMe - Upload Customer Support Transcript
          </DialogTitle>
          <DialogDescription>
            Upload customer support transcripts to help improve our knowledge base.
            Accepted formats: .txt, .log, .html, .htm, or plain text.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Title Field */}
          <div className="space-y-2">
            <Label htmlFor="title">Conversation Title *</Label>
            <Input
              id="title"
              placeholder="e.g., Email Setup Issue - Customer #12345"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={uploadState.isUploading}
              className="focus-visible:ring-accent"
            />
          </div>

          {/* Upload Tabs */}
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="file" disabled={uploadState.isUploading}>
                <FileText className="h-4 w-4 mr-2" />
                Upload File
              </TabsTrigger>
              <TabsTrigger value="text" disabled={uploadState.isUploading}>
                <Upload className="h-4 w-4 mr-2" />
                Paste Text
              </TabsTrigger>
            </TabsList>

            {/* File Upload Tab */}
            <TabsContent value="file" className="space-y-4">
              <div
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onClick={() => document.getElementById('file-input')?.click()}
                className={`
                  border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
                  ${isDragActive ? 'border-accent bg-accent/5' : 'border-muted-foreground/25'}
                  ${uploadedFile ? 'border-accent bg-accent/5' : ''}
                  ${uploadState.isUploading ? 'pointer-events-none opacity-50' : 'hover:border-accent hover:bg-accent/5'}
                `}
              >
                <input
                  id="file-input"
                  type="file"
                  accept=".txt,.log,.html,.htm,text/*"
                  onChange={handleFileInputChange}
                  className="hidden"
                  disabled={uploadState.isUploading}
                />
                <div className="space-y-2">
                  {uploadedFile ? (
                    <>
                      <CheckCircle2 className="h-8 w-8 text-accent mx-auto" />
                      <p className="text-sm font-medium">{uploadedFile.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {(uploadedFile.size / 1024).toFixed(1)} KB
                      </p>
                      {filePreview && filePreview.description && (
                        <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded-md">
                          <p className="text-xs text-blue-700 font-medium">
                            {filePreview.description}
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <>
                      <Upload className="h-8 w-8 text-muted-foreground mx-auto" />
                      <p className="text-sm font-medium">
                        {isDragActive ? 'Drop the file here...' : 'Drag and drop a file here, or click to select'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Supports .txt, .log, .html, .htm files up to 10MB
                      </p>
                    </>
                  )}
                </div>
              </div>
            </TabsContent>

            {/* Text Input Tab */}
            <TabsContent value="text" className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="textContent">Transcript Content *</Label>
                <Textarea
                  id="textContent"
                  placeholder="Paste your customer support transcript here..."
                  value={textContent}
                  onChange={(e) => setTextContent(e.target.value)}
                  disabled={uploadState.isUploading}
                  className="min-h-[200px] focus-visible:ring-accent"
                />
                <p className="text-xs text-muted-foreground">
                  {textContent.length} characters
                </p>
              </div>
            </TabsContent>
          </Tabs>

          {/* Upload Progress */}
          {uploadState.isUploading && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span>Uploading transcript...</span>
                <span>{uploadState.progress}%</span>
              </div>
              <Progress value={uploadState.progress} className="h-2" />
            </div>
          )}

          {/* Error Alert */}
          {uploadState.error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{uploadState.error}</AlertDescription>
            </Alert>
          )}

          {/* Success Alert */}
          {uploadState.success && (
            <Alert className="border-green-200 text-green-800 bg-green-50">
              <CheckCircle2 className="h-4 w-4" />
              <AlertDescription>
                Transcript uploaded successfully! 
                {uploadState.conversationId && (
                  <> Conversation ID: {uploadState.conversationId}.</>
                )}
                {uploadState.processingStatus && (
                  <> Status: {uploadState.processingStatus}.</>
                )}
                {uploadState.processingStatus === 'completed' 
                  ? ' Processing complete - examples are now available for searches!'
                  : ' Processing will continue in the background.'
                }
              </AlertDescription>
            </Alert>
          )}

          {/* Action Buttons */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={uploadState.isUploading}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!isValid() || uploadState.isUploading}
              className="bg-accent hover:bg-accent/90"
            >
              {uploadState.isUploading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4 mr-2" />
                  Upload Transcript
                </>
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}