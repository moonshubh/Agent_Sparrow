/**
 * Folder Debugger Component
 * Debug folder operations to identify issues
 */

'use client'

import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { createFolderSupabase, deleteFolderSupabase, listFolders, uploadTranscriptFile } from '@/lib/feedme-api'
import { useFoldersActions } from '@/lib/stores/folders-store'

export function FolderDebugger() {
  const [folderName, setFolderName] = useState('')
  const [folderId, setFolderId] = useState('')
  const [testResults, setTestResults] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  
  const foldersActions = useFoldersActions()

  const addResult = (result: string) => {
    setTestResults(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${result}`])
  }

  const testListFolders = async () => {
    setIsLoading(true)
    addResult('Testing list folders endpoint...')
    
    try {
      const response = await listFolders()
      addResult(`✅ List folders successful: ${response.folders.length} folders found`)
      console.log('List folders response:', response)
    } catch (error) {
      addResult(`❌ List folders failed: ${error}`)
      console.error('List folders error:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const testCreateFolderDirect = async () => {
    if (!folderName.trim()) {
      addResult('❌ Please enter a folder name')
      return
    }

    setIsLoading(true)
    addResult(`Testing create folder directly via API: "${folderName}"...`)
    
    try {
      const response = await createFolderSupabase({
        name: folderName,
        color: '#0095ff',
        description: 'Test folder created via debugger'
      })
      addResult(`✅ Create folder API successful: ID ${response.folder?.id || 'unknown'}`)
      console.log('Create folder API response:', response)
    } catch (error) {
      addResult(`❌ Create folder API failed: ${error}`)
      console.error('Create folder API error:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const testCreateFolderStore = async () => {
    if (!folderName.trim()) {
      addResult('❌ Please enter a folder name')
      return
    }

    setIsLoading(true)
    addResult(`Testing create folder via store: "${folderName}"...`)
    
    try {
      const folder = await foldersActions.createFolder({
        name: folderName + ' (Store)',
        color: '#38b6ff',
        description: 'Test folder created via store'
      })
      addResult(`✅ Create folder store successful: ID ${folder.id}`)
      console.log('Create folder store response:', folder)
    } catch (error) {
      addResult(`❌ Create folder store failed: ${error}`)
      console.error('Create folder store error:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const testDeleteFolder = async () => {
    if (!folderId.trim()) {
      addResult('❌ Please enter a folder ID')
      return
    }

    setIsLoading(true)
    addResult(`Testing delete folder: ID ${folderId}...`)
    
    try {
      const response = await deleteFolderSupabase(parseInt(folderId))
      addResult(`✅ Delete folder successful`)
      console.log('Delete folder response:', response)
    } catch (error) {
      addResult(`❌ Delete folder failed: ${error}`)
      console.error('Delete folder error:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const testEndpoints = async () => {
    setIsLoading(true)
    addResult('Testing all endpoints...')
    
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api/v1'
    const endpoints = [
      '/feedme/folders',
      '/feedme/folders/create',
      '/feedme/conversations',
      '/feedme/analytics'
    ]
    
    for (const endpoint of endpoints) {
      try {
        const response = await fetch(`${baseUrl}${endpoint}`)
        addResult(`${response.ok ? '✅' : '❌'} ${endpoint}: ${response.status} ${response.statusText}`)
      } catch (error) {
        addResult(`❌ ${endpoint}: ${error}`)
      }
    }
    
    // Test PDF config
    try {
      const response = await fetch(`${baseUrl}/feedme/analytics`)
      if (response.ok) {
        const data = await response.json()
        addResult(`PDF Support: ${data.pdf_enabled ? '✅ Enabled' : '❌ Disabled'}`)
      }
    } catch (error) {
      addResult(`❌ Could not check PDF support: ${error}`)
    }
    
    setIsLoading(false)
  }

  const clearResults = () => {
    setTestResults([])
  }
  
  const testPdfUploadDirect = async () => {
    if (!selectedFile) {
      addResult('❌ Please select a PDF file first')
      return
    }
    
    setIsLoading(true)
    addResult(`Testing direct PDF upload to API...`)
    
    const formData = new FormData()
    formData.append('title', selectedFile.name.replace(/\.pdf$/i, ''))
    formData.append('transcript_file', selectedFile)
    formData.append('auto_process', 'true')
    formData.append('uploaded_by', 'debugger')
    
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api/v1'
    
    try {
      const response = await fetch(`${baseUrl}/feedme/conversations/upload`, {
        method: 'POST',
        body: formData,
      })
      
      const responseText = await response.text()
      let responseData: any
      try {
        responseData = JSON.parse(responseText)
      } catch {
        responseData = { raw: responseText }
      }
      
      if (!response.ok) {
        addResult(`❌ Direct upload failed: ${response.status} ${response.statusText}`)
        addResult(`Error response: ${JSON.stringify(responseData, null, 2)}`)
      } else {
        addResult(`✅ Direct upload successful: ID ${responseData.id}`)
        addResult(`Processing status: ${responseData.processing_status}`)
      }
    } catch (error) {
      addResult(`❌ Direct upload error: ${error}`)
      if (error instanceof Error) {
        addResult(`Error stack: ${error.stack}`)
      }
    } finally {
      setIsLoading(false)
    }
  }
  
  const testPdfUpload = async () => {
    if (!selectedFile) {
      addResult('❌ Please select a file first')
      return
    }
    
    setIsLoading(true)
    addResult(`Testing file upload: "${selectedFile.name}"...`)
    addResult(`File size: ${(selectedFile.size / 1024 / 1024).toFixed(2)} MB`)
    addResult(`File type: ${selectedFile.type || 'unknown'}`)
    
    try {
      // Remove file extension for title
      const title = selectedFile.name.replace(/\.(pdf|txt)$/i, '')
      
      const response = await uploadTranscriptFile(
        title,          // title first
        selectedFile,   // file second
        'debugger',
        true
      )
      addResult(`✅ File upload successful: Conversation ID ${response.id}`)
      addResult(`Processing status: ${response.processing_status}`)
      console.log('File upload response:', response)
    } catch (error) {
      addResult(`❌ File upload failed: ${error}`)
      // Try to extract more error details
      if (error instanceof Error) {
        addResult(`Error type: ${error.name}`)
        addResult(`Error message: ${error.message}`)
        if ('cause' in error && error.cause) {
          addResult(`Error cause: ${error.cause}`)
        }
      }
      console.error('File upload error:', error)
    } finally {
      setIsLoading(false)
    }
  }
  
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
      addResult(`Selected file: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`)
    }
  }

  return (
    <Card className="m-4">
      <CardHeader>
        <CardTitle>Folder Operations Debugger</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label>Folder Name</Label>
          <Input
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            placeholder="Enter folder name for create tests"
          />
        </div>
        
        <div className="space-y-2">
          <Label>Folder ID</Label>
          <Input
            value={folderId}
            onChange={(e) => setFolderId(e.target.value)}
            placeholder="Enter folder ID for delete test"
          />
        </div>

        <div className="space-y-2">
          <Label>File Upload Test (PDF/TXT)</Label>
          <div className="flex gap-2">
            <Input
              type="file"
              accept=".pdf,.txt"
              onChange={handleFileSelect}
              className="flex-1"
            />
            <Button onClick={testPdfUpload} disabled={isLoading || !selectedFile} variant="outline">
              Test File Upload
            </Button>
            <Button onClick={testPdfUploadDirect} disabled={isLoading || !selectedFile} variant="outline">
              Test Direct API
            </Button>
          </div>
        </div>
        
        <div className="flex flex-wrap gap-2">
          <Button onClick={testEndpoints} disabled={isLoading} variant="outline">
            Test Endpoints
          </Button>
          <Button onClick={testListFolders} disabled={isLoading} variant="outline">
            Test List Folders
          </Button>
          <Button onClick={testCreateFolderDirect} disabled={isLoading} variant="outline">
            Test Create (API)
          </Button>
          <Button onClick={testCreateFolderStore} disabled={isLoading} variant="outline">
            Test Create (Store)
          </Button>
          <Button onClick={testDeleteFolder} disabled={isLoading} variant="outline">
            Test Delete
          </Button>
          <Button onClick={clearResults} variant="ghost">
            Clear
          </Button>
        </div>

        <div className="mt-4 p-4 bg-muted rounded-lg">
          <h4 className="font-semibold mb-2">Test Results:</h4>
          <div className="space-y-1 font-mono text-sm max-h-96 overflow-y-auto">
            {testResults.length === 0 ? (
              <p className="text-muted-foreground">No tests run yet</p>
            ) : (
              testResults.map((result, index) => (
                <div key={index}>{result}</div>
              ))
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default FolderDebugger