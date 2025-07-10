"use client"

import React, { useState, useCallback, useRef, useEffect } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { 
  Upload, 
  FileText, 
  Loader2, 
  AlertCircle, 
  CheckCircle2, 
  X, 
  File,
  Folder,
  Eye,
  Trash2,
  Plus,
  FileCheck,
  Clock,
  AlertTriangle
} from 'lucide-react'
import { uploadTranscriptFile, uploadTranscriptText, getProcessingStatus } from '@/lib/feedme-api'
import { cn } from '@/lib/utils'

interface EnhancedFeedMeModalProps {
  isOpen: boolean
  onClose: () => void
  onUploadComplete?: (results: UploadResult[]) => void
}

interface FileUploadState {
  file: File
  id: string
  title: string
  status: 'pending' | 'uploading' | 'processing' | 'completed' | 'error'
  progress: number
  error?: string
  conversationId?: number
  processingStatus?: string
  preview?: FilePreview
}

interface FilePreview {
  isHtml: boolean
  isPdf?: boolean
  messageCount?: number
  attachmentCount?: number
  description?: string
  fileSize: string
  lastModified: string
}

interface UploadResult {
  id: number
  title: string
  status: string
  total_examples: number
}

interface BatchUploadState {
  isUploading: boolean
  totalFiles: number
  completedFiles: number
  errors: string[]
  results: UploadResult[]
}

export function EnhancedFeedMeModal({ isOpen, onClose, onUploadComplete }: EnhancedFeedMeModalProps) {
  const [activeTab, setActiveTab] = useState<'multi-file' | 'single-file' | 'text'>('multi-file')
  const [isDragActive, setIsDragActive] = useState(false)
  const [files, setFiles] = useState<FileUploadState[]>([])
  const [batchUploadState, setBatchUploadState] = useState<BatchUploadState>({
    isUploading: false,
    totalFiles: 0,
    completedFiles: 0,
    errors: [],
    results: []
  })
  
  // Single file/text upload states (legacy compatibility)
  const [singleTitle, setSingleTitle] = useState('')
  const [textContent, setTextContent] = useState('')
  const [singleFile, setSingleFile] = useState<File | null>(null)
  const [singleFilePreview, setSingleFilePreview] = useState<FilePreview | null>(null)
  
  const fileInputRef = useRef<HTMLInputElement>(null)
  const userId = process.env.NEXT_PUBLIC_FEEDME_USER_ID || 'web-user'

  // File validation
  const validateFile = useCallback((file: File): string | null => {
    const allowedTypes = ['text/plain', 'text/html', 'application/html', 'text/csv', 'application/pdf', 'application/x-pdf']
    const allowedExtensions = ['.txt', '.log', '.html', '.htm', '.csv', '.pdf']
    
    const hasValidType = file.type === '' || allowedTypes.includes(file.type) || file.type.startsWith('text/')
    const hasValidExtension = allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext))
    
    if (!hasValidType && !hasValidExtension) {
      return 'Invalid file type. We support text files (.txt, .log), HTML files (.html, .htm), CSV files (.csv), and PDF documents (.pdf). Please ensure your file has one of these extensions.'
    }

    // Different size limits for different file types
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
    const maxSize = isPdf ? 20 * 1024 * 1024 : 10 * 1024 * 1024 // 20MB for PDF, 10MB for others
    
    if (file.size > maxSize) {
      return `File size must be less than ${isPdf ? '20MB' : '10MB'}`
    }

    return null
  }, [])

  // File analysis
  const analyzeFile = useCallback(async (file: File): Promise<FilePreview> => {
    const isHtmlFile = file.name.toLowerCase().endsWith('.html') || 
                      file.name.toLowerCase().endsWith('.htm') ||
                      file.type.includes('html')
    
    const isPdfFile = file.name.toLowerCase().endsWith('.pdf') ||
                     file.type === 'application/pdf'
    
    const basePreview: FilePreview = {
      isHtml: isHtmlFile,
      fileSize: formatFileSize(file.size),
      lastModified: new Date(file.lastModified).toLocaleDateString()
    }

    if (isPdfFile) {
      return {
        ...basePreview,
        description: `PDF document detected - ${Math.round(file.size / 1024)}KB`,
        isPdf: true
      }
    }

    if (!isHtmlFile) {
      return {
        ...basePreview,
        description: `Text file detected - ${Math.round(file.size / 1024)}KB`
      }
    }

    try {
      // Handle file.text() method safely for testing environments
      const content = typeof file.text === 'function' 
        ? await file.text()
        : await new Promise<string>((resolve) => {
            const reader = new FileReader()
            reader.onload = () => resolve(reader.result as string)
            reader.readAsText(file)
          })
      
      const parser = new DOMParser()
      const doc = parser.parseFromString(content, 'text/html')
      
      // Check for Zendesk ticket
      const zendeskSelectors = [
        '.zd-comment',
        '[data-test-id="ticket-title"]',
        '[data-creator-name]',
        'meta[name="generator"][content*="Zendesk"]'
      ]
      const isZendeskTicket = zendeskSelectors.some(sel => doc.querySelector(sel)) || 
                             /zendesk|zd-comment/i.test(content)
      
      if (isZendeskTicket) {
        const commentDivs = doc.querySelectorAll('div.zd-comment, .zd-comment')
        const attachmentLinks = doc.querySelectorAll('a[href*="attachment"], a[href*="download"], img')
        const mainBody = doc.querySelector('#html')
        const hasMainContent = mainBody && mainBody.textContent && mainBody.textContent.trim().length > 50
        
        const messageCount = commentDivs.length + (hasMainContent ? 1 : 0)
        
        return {
          ...basePreview,
          messageCount,
          attachmentCount: attachmentLinks.length,
          description: `Zendesk ticket - ${messageCount} message${messageCount !== 1 ? 's' : ''}, ${attachmentLinks.length} attachment${attachmentLinks.length !== 1 ? 's' : ''}`
        }
      } else {
        const textLength = doc.body?.textContent?.length || 0
        return {
          ...basePreview,
          description: `HTML file - ${Math.round(textLength / 100)} content blocks`
        }
      }
    } catch (error) {
      console.warn('Error analyzing HTML file:', error)
      return {
        ...basePreview,
        description: 'HTML file detected'
      }
    }
  }, [])

  // Format file size
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  // Generate unique ID for files
  const generateFileId = (): string => {
    return Date.now().toString(36) + Math.random().toString(36).substr(2)
  }

  // Add files to upload queue
  const addFiles = useCallback(async (newFiles: File[]) => {
    const validFiles: FileUploadState[] = []
    
    for (const file of newFiles) {
      const error = validateFile(file)
      if (error) {
        setBatchUploadState(prev => ({
          ...prev,
          errors: [...prev.errors, `${file.name}: ${error}`]
        }))
        continue
      }

      const id = generateFileId()
      const title = file.name.replace(/\.(txt|log|html|htm|csv)$/i, '')
      const preview = await analyzeFile(file)
      
      validFiles.push({
        file,
        id,
        title,
        status: 'pending',
        progress: 0,
        preview
      })
    }
    
    setFiles(prev => [...prev, ...validFiles])
  }, [validateFile, analyzeFile])

  // Handle file input change
  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || [])
    if (selectedFiles.length > 0) {
      addFiles(selectedFiles)
    }
    // Reset input value to allow re-selecting same files
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }, [addFiles])

  // Drag and drop handlers
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragActive(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragActive(false)
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragActive(false)

    const droppedFiles = Array.from(e.dataTransfer.files)
    if (droppedFiles.length > 0) {
      addFiles(droppedFiles)
    }
  }, [addFiles])

  // Remove file from queue
  const removeFile = useCallback((fileId: string) => {
    setFiles(prev => prev.filter(f => f.id !== fileId))
  }, [])

  // Update file title
  const updateFileTitle = useCallback((fileId: string, newTitle: string) => {
    setFiles(prev => prev.map(f => 
      f.id === fileId ? { ...f, title: newTitle } : f
    ))
  }, [])

  // Upload single file
  const uploadSingleFile = useCallback(async (fileState: FileUploadState): Promise<void> => {
    setFiles(prev => prev.map(f => 
      f.id === fileState.id 
        ? { ...f, status: 'uploading', progress: 20 }
        : f
    ))

    try {
      const uploadResponse = await uploadTranscriptFile(
        fileState.title,
        fileState.file,
        userId,
        true
      )

      setFiles(prev => prev.map(f => 
        f.id === fileState.id 
          ? { 
              ...f, 
              status: 'processing',
              progress: 60,
              conversationId: uploadResponse.id,
              processingStatus: uploadResponse.processing_status
            }
          : f
      ))

      // Poll for processing completion
      let delay = 1000
      let statusResponse: any = null
      while (true) {
        try {
          statusResponse = await getProcessingStatus(uploadResponse.id)
          setFiles(prev => prev.map(f => 
            f.id === fileState.id 
              ? { ...f, processingStatus: statusResponse.status }
              : f
          ))
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

      setFiles(prev => prev.map(f => 
        f.id === fileState.id 
          ? { 
              ...f, 
              status: 'completed',
              progress: 100,
              processingStatus: statusResponse?.status || f.processingStatus
            }
          : f
      ))

      setBatchUploadState(prev => ({
        ...prev,
        completedFiles: prev.completedFiles + 1,
        results: [...prev.results, {
          id: uploadResponse.id,
          title: fileState.title,
          status: statusResponse?.status || 'completed',
          total_examples: uploadResponse.total_examples || 0
        }]
      }))

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Upload failed'
      setFiles(prev => prev.map(f => 
        f.id === fileState.id 
          ? { 
              ...f, 
              status: 'error',
              progress: 0,
              error: errorMessage
            }
          : f
      ))
      setBatchUploadState(prev => ({
        ...prev,
        errors: [...prev.errors, `${fileState.title}: ${errorMessage}`]
      }))
    }
  }, [userId])

  // Batch upload all files
  const handleBatchUpload = useCallback(async () => {
    if (files.length === 0) return

    setBatchUploadState({
      isUploading: true,
      totalFiles: files.length,
      completedFiles: 0,
      errors: [],
      results: []
    })

    // Upload files sequentially to avoid overwhelming the server
    for (const fileState of files) {
      if (fileState.status === 'pending') {
        await uploadSingleFile(fileState)
      }
    }

    setBatchUploadState(prev => ({
      ...prev,
      isUploading: false
    }))

    // Auto-close after successful batch upload
    if (batchUploadState.errors.length === 0) {
      setTimeout(() => {
        handleClose()
      }, 3000)
    }
  }, [files, uploadSingleFile, batchUploadState.errors.length])

  // Reset form
  const resetForm = useCallback(() => {
    setFiles([])
    setSingleTitle('')
    setTextContent('')
    setSingleFile(null)
    setSingleFilePreview(null)
    setBatchUploadState({
      isUploading: false,
      totalFiles: 0,
      completedFiles: 0,
      errors: [],
      results: []
    })
    setActiveTab('multi-file')
  }, [])

  // Handle modal close
  const handleClose = useCallback(() => {
    if (!batchUploadState.isUploading) {
      if (onUploadComplete && batchUploadState.results.length > 0) {
        onUploadComplete(batchUploadState.results)
      }
      resetForm()
      onClose()
    }
  }, [batchUploadState.isUploading, batchUploadState.results, onUploadComplete, resetForm, onClose])

  // Legacy single file upload handler
  const handleSingleFileUpload = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!singleTitle.trim() || !singleFile) {
      return
    }

    const fileState: FileUploadState = {
      file: singleFile,
      id: generateFileId(),
      title: singleTitle,
      status: 'pending',
      progress: 0,
      preview: singleFilePreview || undefined
    }

    setFiles([fileState])
    setBatchUploadState({
      isUploading: true,
      totalFiles: 1,
      completedFiles: 0,
      errors: [],
      results: []
    })

    await uploadSingleFile(fileState)
    
    setBatchUploadState(prev => ({
      ...prev,
      isUploading: false
    }))
  }, [singleTitle, singleFile, singleFilePreview, uploadSingleFile])

  // Handle single file selection (legacy)
  const handleSingleFileSelect = useCallback(async (file: File) => {
    const error = validateFile(file)
    if (!error) {
      setSingleFile(file)
      if (!singleTitle.trim()) {
        setSingleTitle(file.name.replace(/\.(txt|log|html|htm|csv)$/i, ''))
      }
      const preview = await analyzeFile(file)
      setSingleFilePreview(preview)
    }
  }, [validateFile, analyzeFile, singleTitle])

  // Get status icon for file
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-green-600" />
      case 'uploading':
      case 'processing':
        return <Loader2 className="h-4 w-4 text-blue-600 animate-spin" />
      case 'error':
        return <AlertCircle className="h-4 w-4 text-red-600" />
      default:
        return <Clock className="h-4 w-4 text-gray-400" />
    }
  }

  // Get status color
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'text-green-600 bg-green-50 border-green-200'
      case 'uploading':
      case 'processing':
        return 'text-blue-600 bg-blue-50 border-blue-200'
      case 'error':
        return 'text-red-600 bg-red-50 border-red-200'
      default:
        return 'text-gray-600 bg-gray-50 border-gray-200'
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => {
      if (!open && !batchUploadState.isUploading) {
        handleClose()
      }
    }}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-accent">
            <Upload className="h-5 w-5" />
            Enhanced FeedMe Upload
          </DialogTitle>
          <DialogDescription>
            Upload customer support transcripts with advanced multi-file support, real-time preview, and batch processing.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as any)} className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="multi-file" disabled={batchUploadState.isUploading}>
              <Folder className="h-4 w-4 mr-2" />
              Multi-File Upload
            </TabsTrigger>
            <TabsTrigger value="single-file" disabled={batchUploadState.isUploading}>
              <FileText className="h-4 w-4 mr-2" />
              Single File
            </TabsTrigger>
            <TabsTrigger value="text" disabled={batchUploadState.isUploading}>
              <FileCheck className="h-4 w-4 mr-2" />
              Paste Text
            </TabsTrigger>
          </TabsList>

          {/* Multi-File Upload Tab */}
          <TabsContent value="multi-file" className="flex-1 flex flex-col overflow-hidden mt-4">
            <div className="flex-1 flex flex-col gap-4 overflow-hidden">
              {/* Drop Zone */}
              <div
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
                  isDragActive ? "border-accent bg-accent/5" : "border-muted-foreground/25",
                  files.length > 0 ? "border-accent bg-accent/5" : "",
                  batchUploadState.isUploading ? "pointer-events-none opacity-50" : "hover:border-accent hover:bg-accent/5"
                )}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".txt,.log,.html,.htm,.csv,.pdf,text/*"
                  onChange={handleFileInputChange}
                  className="hidden"
                  disabled={batchUploadState.isUploading}
                />
                <div className="space-y-2">
                  <Upload className="h-8 w-8 text-muted-foreground mx-auto" />
                  <p className="text-sm font-medium">
                    {isDragActive ? 'Drop files here...' : 'Drag and drop files here, or click to select'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Supports multiple .txt, .log, .html, .htm, .csv, and .pdf files (up to 10MB for text files, 20MB for PDFs)
                  </p>
                </div>
              </div>

              {/* File List */}
              {files.length > 0 && (
                <div className="flex-1 overflow-hidden">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-medium">Files ({files.length})</h4>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setFiles([])}
                        disabled={batchUploadState.isUploading}
                      >
                        Clear All
                      </Button>
                      <Button
                        onClick={handleBatchUpload}
                        disabled={files.length === 0 || batchUploadState.isUploading}
                        className="bg-accent hover:bg-accent/90"
                        size="sm"
                      >
                        {batchUploadState.isUploading ? (
                          <>
                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                            Uploading ({batchUploadState.completedFiles}/{batchUploadState.totalFiles})
                          </>
                        ) : (
                          <>
                            <Upload className="h-4 w-4 mr-2" />
                            Upload All
                          </>
                        )}
                      </Button>
                    </div>
                  </div>

                  <ScrollArea className="h-[300px]">
                    <div className="space-y-3 pr-4">
                      {files.map((fileState) => (
                        <Card key={fileState.id} className="transition-all hover:shadow-md">
                          <CardHeader className="pb-2">
                            <div className="flex items-start justify-between">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <File className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                                  <Input
                                    value={fileState.title}
                                    onChange={(e) => updateFileTitle(fileState.id, e.target.value)}
                                    disabled={fileState.status !== 'pending'}
                                    className="h-7 text-sm border-0 p-0 focus-visible:ring-0"
                                  />
                                </div>
                                <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                                  <span>{fileState.file.name}</span>
                                  {fileState.preview && (
                                    <span>{fileState.preview.fileSize}</span>
                                  )}
                                </div>
                              </div>
                              
                              <div className="flex items-center gap-2 ml-2 flex-shrink-0">
                                <Badge 
                                  variant="outline" 
                                  className={cn("text-xs", getStatusColor(fileState.status))}
                                >
                                  <span className="mr-1">{getStatusIcon(fileState.status)}</span>
                                  {fileState.status}
                                </Badge>
                                {fileState.status === 'pending' && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => removeFile(fileState.id)}
                                    className="h-6 w-6 p-0 text-red-500 hover:text-red-700"
                                  >
                                    <X className="h-3 w-3" />
                                  </Button>
                                )}
                              </div>
                            </div>
                          </CardHeader>

                          <CardContent className="pt-0">
                            {fileState.preview && fileState.preview.description && (
                              <div className="mb-2 p-2 bg-blue-50 border border-blue-200 rounded-md">
                                <p className="text-xs text-blue-700 font-medium">
                                  {fileState.preview.description}
                                </p>
                              </div>
                            )}
                            
                            {(fileState.status === 'uploading' || fileState.status === 'processing') && (
                              <div className="space-y-2">
                                <div className="flex items-center justify-between text-xs">
                                  <span>
                                    {fileState.status === 'uploading' ? 'Uploading...' : 'Processing...'}
                                  </span>
                                  <span>{fileState.progress}%</span>
                                </div>
                                <Progress value={fileState.progress} className="h-1" />
                              </div>
                            )}
                            
                            {fileState.error && (
                              <Alert variant="destructive" className="mt-2">
                                <AlertCircle className="h-4 w-4" />
                                <AlertDescription className="text-xs">{fileState.error}</AlertDescription>
                              </Alert>
                            )}
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              )}

              {/* Batch Upload Progress */}
              {batchUploadState.isUploading && (
                <div className="space-y-2 p-4 bg-blue-50 border border-blue-200 rounded-md">
                  <div className="flex items-center justify-between text-sm">
                    <span>Batch Upload Progress</span>
                    <span>{batchUploadState.completedFiles}/{batchUploadState.totalFiles} completed</span>
                  </div>
                  <Progress 
                    value={(batchUploadState.completedFiles / batchUploadState.totalFiles) * 100} 
                    className="h-2" 
                  />
                </div>
              )}

              {/* Results Summary */}
              {batchUploadState.results.length > 0 && (
                <Alert className="border-green-200 text-green-800 bg-green-50">
                  <CheckCircle2 className="h-4 w-4" />
                  <AlertDescription>
                    Successfully uploaded {batchUploadState.results.length} file{batchUploadState.results.length !== 1 ? 's' : ''}!
                    {batchUploadState.results.reduce((total, result) => total + result.total_examples, 0)} examples extracted.
                  </AlertDescription>
                </Alert>
              )}

              {/* Error Summary */}
              {batchUploadState.errors.length > 0 && (
                <Alert variant="destructive">
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    <div className="space-y-1">
                      <p className="font-medium">{batchUploadState.errors.length} error{batchUploadState.errors.length !== 1 ? 's' : ''} occurred:</p>
                      {batchUploadState.errors.map((error, index) => (
                        <p key={index} className="text-xs">{error}</p>
                      ))}
                    </div>
                  </AlertDescription>
                </Alert>
              )}
            </div>
          </TabsContent>

          {/* Single File Tab (Legacy Compatibility) */}
          <TabsContent value="single-file" className="flex-1 overflow-auto mt-4">
            <form onSubmit={handleSingleFileUpload} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="single-title">Conversation Title *</Label>
                <Input
                  id="single-title"
                  placeholder="e.g., Email Setup Issue - Customer #12345"
                  value={singleTitle}
                  onChange={(e) => setSingleTitle(e.target.value)}
                  disabled={batchUploadState.isUploading}
                  className="focus-visible:ring-accent"
                />
              </div>

              <div
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={(e) => {
                  handleDrop(e)
                  const files = Array.from(e.dataTransfer.files)
                  if (files.length > 0) {
                    handleSingleFileSelect(files[0])
                  }
                }}
                onClick={() => document.getElementById('single-file-input')?.click()}
                className={cn(
                  "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
                  isDragActive ? "border-accent bg-accent/5" : "border-muted-foreground/25",
                  singleFile ? "border-accent bg-accent/5" : "",
                  batchUploadState.isUploading ? "pointer-events-none opacity-50" : "hover:border-accent hover:bg-accent/5"
                )}
              >
                <input
                  id="single-file-input"
                  type="file"
                  accept=".txt,.log,.html,.htm,.csv,.pdf,text/*"
                  onChange={(e) => {
                    const files = e.target.files
                    if (files && files.length > 0) {
                      handleSingleFileSelect(files[0])
                    }
                  }}
                  className="hidden"
                  disabled={batchUploadState.isUploading}
                />
                <div className="space-y-2">
                  {singleFile ? (
                    <>
                      <CheckCircle2 className="h-8 w-8 text-accent mx-auto" />
                      <p className="text-sm font-medium">{singleFile.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatFileSize(singleFile.size)}
                      </p>
                      {singleFilePreview && singleFilePreview.description && (
                        <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded-md">
                          <p className="text-xs text-blue-700 font-medium">
                            {singleFilePreview.description}
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
                        Supports .txt, .log, .html, .htm, .csv, and .pdf files (up to 10MB for text files, 20MB for PDFs)
                      </p>
                    </>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleClose}
                  disabled={batchUploadState.isUploading}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={!singleTitle.trim() || !singleFile || batchUploadState.isUploading}
                  className="bg-accent hover:bg-accent/90"
                >
                  {batchUploadState.isUploading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      Upload File
                    </>
                  )}
                </Button>
              </div>
            </form>
          </TabsContent>

          {/* Text Input Tab */}
          <TabsContent value="text" className="flex-1 overflow-auto mt-4">
            <form onSubmit={async (e) => {
              e.preventDefault()
              if (!singleTitle.trim() || !textContent.trim()) return
              
              setBatchUploadState({
                isUploading: true,
                totalFiles: 1,
                completedFiles: 0,
                errors: [],
                results: []
              })

              try {
                const uploadResponse = await uploadTranscriptText(
                  singleTitle,
                  textContent,
                  userId,
                  true
                )
                
                setBatchUploadState(prev => ({
                  ...prev,
                  isUploading: false,
                  completedFiles: 1,
                  results: [{
                    id: uploadResponse.id,
                    title: singleTitle,
                    status: uploadResponse.processing_status,
                    total_examples: uploadResponse.total_examples || 0
                  }]
                }))

                setTimeout(() => {
                  handleClose()
                }, 3000)
              } catch (error) {
                const errorMessage = error instanceof Error ? error.message : 'Upload failed'
                setBatchUploadState(prev => ({
                  ...prev,
                  isUploading: false,
                  errors: [errorMessage]
                }))
              }
            }} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="text-title">Conversation Title *</Label>
                <Input
                  id="text-title"
                  placeholder="e.g., Email Setup Issue - Customer #12345"
                  value={singleTitle}
                  onChange={(e) => setSingleTitle(e.target.value)}
                  disabled={batchUploadState.isUploading}
                  className="focus-visible:ring-accent"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="text-content">Transcript Content *</Label>
                <Textarea
                  id="text-content"
                  placeholder="Paste your customer support transcript here..."
                  value={textContent}
                  onChange={(e) => setTextContent(e.target.value)}
                  disabled={batchUploadState.isUploading}
                  className="min-h-[300px] focus-visible:ring-accent"
                />
                <p className="text-xs text-muted-foreground">
                  {textContent.length} characters
                </p>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleClose}
                  disabled={batchUploadState.isUploading}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={!singleTitle.trim() || !textContent.trim() || batchUploadState.isUploading}
                  className="bg-accent hover:bg-accent/90"
                >
                  {batchUploadState.isUploading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      Upload Text
                    </>
                  )}
                </Button>
              </div>
            </form>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}