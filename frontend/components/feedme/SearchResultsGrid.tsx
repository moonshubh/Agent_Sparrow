/**
 * SearchResultsGrid Component
 * 
 * Rich result cards with relevance scoring, infinite scroll with virtualization,
 * preview modal for quick content review, and export selected results functionality.
 * 
 * Part of FeedMe v2.0 Phase 3D: Advanced Search Interface
 */

'use client'

import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { FixedSizeGrid as Grid } from 'react-window'
import InfiniteLoader from 'react-window-infinite-loader'
import { 
  Star, Eye, Download, ExternalLink, Clock, CheckCircle2,
  Filter, SortAsc, Grid3X3, List, MoreHorizontal, Share,
  FileText, MessageCircle, Tag, Calendar, User, Zap,
  ArrowUpDown, TrendingUp, Search, X, Plus, Minus
} from 'lucide-react'
import { useSearch, useActions } from '@/lib/stores/feedme-store'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

// Types
interface SearchResultsGridProps {
  results: SearchResult[]
  totalResults: number
  isLoading: boolean
  hasNextPage?: boolean
  onLoadMore?: () => Promise<void>
  onResultSelect?: (resultId: string) => void
  onResultPreview?: (resultId: string) => void
  onExportSelected?: (resultIds: string[]) => void
  enableInfiniteScroll?: boolean
  enableVirtualization?: boolean
  itemsPerRow?: number
  className?: string
}

interface SearchResult {
  id: string
  type: 'conversation' | 'qa_pair' | 'example'
  title: string
  content: string
  snippet: string
  score: number
  relevanceFactors: RelevanceFactor[]
  metadata: ResultMetadata
  highlights: string[]
  tags: string[]
  source: {
    id: string
    name: string
    type: 'file' | 'folder' | 'system'
  }
  createdAt: string
  updatedAt: string
}

interface RelevanceFactor {
  type: 'keyword_match' | 'semantic_similarity' | 'context_relevance' | 'quality_score'
  score: number
  weight: number
  description: string
}

interface ResultMetadata {
  platform?: string
  confidence?: number
  qualityScore?: number
  sentiment?: 'positive' | 'neutral' | 'negative'
  category?: string
  priority?: 'high' | 'medium' | 'low'
  processingStatus?: 'completed' | 'processing' | 'failed'
  approvalStatus?: 'approved' | 'pending' | 'rejected'
  wordCount?: number
  exampleCount?: number
}

interface GridItemProps {
  columnIndex: number
  rowIndex: number
  style: React.CSSProperties
  data: {
    results: SearchResult[]
    itemsPerRow: number
    selectedResults: Set<string>
    onSelect: (resultId: string, selected: boolean) => void
    onPreview: (resultId: string) => void
    viewMode: 'grid' | 'list'
  }
}

// Relevance Score Component
const RelevanceScoreIndicator: React.FC<{ 
  score: number,
  factors: RelevanceFactor[],
  showDetails?: boolean
}> = ({ score, factors, showDetails = false }) => {
  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-green-600 bg-green-100'
    if (score >= 0.6) return 'text-yellow-600 bg-yellow-100'
    return 'text-red-600 bg-red-100'
  }

  const scorePercentage = Math.round(score * 100)

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <div className={cn(
            'flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium',
            getScoreColor(score)
          )}>
            <Star className="h-3 w-3" />
            {scorePercentage}%
          </div>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <div className="space-y-2">
            <p className="font-medium">Relevance Score: {scorePercentage}%</p>
            {showDetails && (
              <div className="space-y-1 text-xs">
                {factors.map((factor, index) => (
                  <div key={index} className="flex justify-between">
                    <span>{factor.description}:</span>
                    <span>{Math.round(factor.score * 100)}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

// Result Type Badge
const ResultTypeBadge: React.FC<{ type: SearchResult['type'] }> = ({ type }) => {
  const config = {
    conversation: { icon: MessageCircle, label: 'Conversation', color: 'bg-blue-100 text-blue-800' },
    qa_pair: { icon: FileText, label: 'Q&A Pair', color: 'bg-green-100 text-green-800' },
    example: { icon: Zap, label: 'Example', color: 'bg-purple-100 text-purple-800' }
  }

  const { icon: Icon, label, color } = config[type]

  return (
    <Badge variant="secondary" className={cn('text-xs', color)}>
      <Icon className="h-3 w-3 mr-1" />
      {label}
    </Badge>
  )
}

// Metadata Display Component
const MetadataDisplay: React.FC<{ metadata: ResultMetadata }> = ({ metadata }) => {
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      {metadata.platform && (
        <span className="capitalize">{metadata.platform}</span>
      )}
      {metadata.confidence && (
        <span>{Math.round(metadata.confidence * 100)}% conf</span>
      )}
      {metadata.qualityScore && (
        <span>{Math.round(metadata.qualityScore * 100)}% quality</span>
      )}
      {metadata.sentiment && (
        <Badge variant="outline" className={cn(
          'text-xs',
          metadata.sentiment === 'positive' && 'text-green-600',
          metadata.sentiment === 'negative' && 'text-red-600'
        )}>
          {metadata.sentiment}
        </Badge>
      )}
    </div>
  )
}

// Highlights Component
const HighlightsDisplay: React.FC<{ 
  content: string, 
  highlights: string[],
  maxLength?: number 
}> = ({ content, highlights, maxLength = 200 }) => {
  const highlightedContent = useMemo(() => {
    let result = content
    
    // Truncate if needed
    if (result.length > maxLength) {
      result = result.substring(0, maxLength) + '...'
    }
    
    // Apply highlights
    highlights.forEach(highlight => {
      const regex = new RegExp(`(${highlight})`, 'gi')
      result = result.replace(regex, '<mark>$1</mark>')
    })
    
    return result
  }, [content, highlights, maxLength])

  return (
    <div 
      className="text-sm leading-relaxed"
      dangerouslySetInnerHTML={{ __html: highlightedContent }}
    />
  )
}

// Grid Item Component
const GridItem: React.FC<GridItemProps> = ({ columnIndex, rowIndex, style, data }) => {
  const { results, itemsPerRow, selectedResults, onSelect, onPreview, viewMode } = data
  const index = rowIndex * itemsPerRow + columnIndex
  const result = results[index]

  if (!result) {
    return <div style={style} />
  }

  const isSelected = selectedResults.has(result.id)
  const [isHovered, setIsHovered] = useState(false)

  const handleSelect = useCallback((checked: boolean) => {
    onSelect(result.id, checked)
  }, [result.id, onSelect])

  const handlePreview = useCallback(() => {
    onPreview(result.id)
  }, [result.id, onPreview])

  if (viewMode === 'list') {
    return (
      <div style={style} className="p-2">
        <Card className={cn(
          'transition-all duration-200 cursor-pointer',
          isSelected && 'ring-2 ring-accent shadow-md',
          'hover:shadow-sm'
        )}>
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <Checkbox
                checked={isSelected}
                onCheckedChange={handleSelect}
                onClick={(e) => e.stopPropagation()}
              />
              
              <div className="flex-1 min-w-0 space-y-2">
                {/* Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <ResultTypeBadge type={result.type} />
                    <h3 className="font-medium text-sm truncate">{result.title}</h3>
                  </div>
                  <RelevanceScoreIndicator 
                    score={result.score} 
                    factors={result.relevanceFactors}
                    showDetails 
                  />
                </div>

                {/* Content */}
                <HighlightsDisplay 
                  content={result.snippet} 
                  highlights={result.highlights}
                  maxLength={150}
                />

                {/* Tags */}
                {result.tags.length > 0 && (
                  <div className="flex gap-1 flex-wrap">
                    {result.tags.slice(0, 3).map(tag => (
                      <Badge key={tag} variant="outline" className="text-xs">
                        {tag}
                      </Badge>
                    ))}
                    {result.tags.length > 3 && (
                      <Badge variant="outline" className="text-xs">
                        +{result.tags.length - 3}
                      </Badge>
                    )}
                  </div>
                )}

                {/* Footer */}
                <div className="flex items-center justify-between">
                  <MetadataDisplay metadata={result.metadata} />
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handlePreview}
                      className="h-6 px-2"
                    >
                      <Eye className="h-3 w-3" />
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
                          <MoreHorizontal className="h-3 w-3" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={handlePreview}>
                          <Eye className="h-3 w-3 mr-2" />
                          Preview
                        </DropdownMenuItem>
                        <DropdownMenuItem>
                          <ExternalLink className="h-3 w-3 mr-2" />
                          Open
                        </DropdownMenuItem>
                        <DropdownMenuItem>
                          <Share className="h-3 w-3 mr-2" />
                          Share
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem>
                          <Download className="h-3 w-3 mr-2" />
                          Export
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Grid view
  return (
    <div style={style} className="p-2">
      <Card 
        className={cn(
          'h-full transition-all duration-200 cursor-pointer',
          isSelected && 'ring-2 ring-accent shadow-md',
          'hover:shadow-md hover:scale-[1.02]',
          'group'
        )}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={handlePreview}
      >
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <Checkbox
              checked={isSelected}
              onCheckedChange={handleSelect}
              onClick={(e) => e.stopPropagation()}
              className="flex-shrink-0"
            />
            <RelevanceScoreIndicator 
              score={result.score} 
              factors={result.relevanceFactors}
            />
          </div>
        </CardHeader>

        <CardContent className="pt-0 space-y-3">
          {/* Type and Title */}
          <div>
            <ResultTypeBadge type={result.type} />
            <h3 className="font-medium text-sm mt-1 line-clamp-2">{result.title}</h3>
          </div>

          {/* Content Preview */}
          <HighlightsDisplay 
            content={result.snippet} 
            highlights={result.highlights}
            maxLength={120}
          />

          {/* Tags */}
          {result.tags.length > 0 && (
            <div className="flex gap-1 flex-wrap">
              {result.tags.slice(0, 2).map(tag => (
                <Badge key={tag} variant="outline" className="text-xs">
                  {tag}
                </Badge>
              ))}
              {result.tags.length > 2 && (
                <Badge variant="outline" className="text-xs">
                  +{result.tags.length - 2}
                </Badge>
              )}
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{new Date(result.createdAt).toLocaleDateString()}</span>
            {(isHovered || isSelected) && (
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation()
                    handlePreview()
                  }}
                  className="h-5 w-5 p-0"
                >
                  <Eye className="h-3 w-3" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 w-5 p-0"
                  onClick={(e) => e.stopPropagation()}
                >
                  <MoreHorizontal className="h-3 w-3" />
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// Preview Modal Component
const PreviewModal: React.FC<{
  result: SearchResult | null
  isOpen: boolean
  onClose: () => void
}> = ({ result, isOpen, onClose }) => {
  if (!result) return null

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[80vh] overflow-hidden">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <ResultTypeBadge type={result.type} />
            <DialogTitle className="flex-1">{result.title}</DialogTitle>
            <RelevanceScoreIndicator 
              score={result.score} 
              factors={result.relevanceFactors}
              showDetails
            />
          </div>
          <DialogDescription className="flex items-center gap-4 text-sm">
            <span>Source: {result.source.name}</span>
            <span>Created: {new Date(result.createdAt).toLocaleDateString()}</span>
            {result.metadata.platform && (
              <span>Platform: {result.metadata.platform}</span>
            )}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="max-h-96 mt-4">
          <div className="space-y-4">
            {/* Content */}
            <div>
              <h4 className="font-medium mb-2">Content</h4>
              <div className="p-3 bg-muted rounded text-sm leading-relaxed">
                {result.content}
              </div>
            </div>

            {/* Metadata */}
            <div>
              <h4 className="font-medium mb-2">Metadata</h4>
              <div className="grid grid-cols-2 gap-4 text-sm">
                {result.metadata.confidence && (
                  <div>
                    <span className="text-muted-foreground">Confidence:</span>
                    <span className="ml-2 font-medium">{Math.round(result.metadata.confidence * 100)}%</span>
                  </div>
                )}
                {result.metadata.qualityScore && (
                  <div>
                    <span className="text-muted-foreground">Quality:</span>
                    <span className="ml-2 font-medium">{Math.round(result.metadata.qualityScore * 100)}%</span>
                  </div>
                )}
                {result.metadata.wordCount && (
                  <div>
                    <span className="text-muted-foreground">Words:</span>
                    <span className="ml-2 font-medium">{result.metadata.wordCount}</span>
                  </div>
                )}
                {result.metadata.category && (
                  <div>
                    <span className="text-muted-foreground">Category:</span>
                    <span className="ml-2 font-medium">{result.metadata.category}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Tags */}
            {result.tags.length > 0 && (
              <div>
                <h4 className="font-medium mb-2">Tags</h4>
                <div className="flex gap-1 flex-wrap">
                  {result.tags.map(tag => (
                    <Badge key={tag} variant="outline" className="text-xs">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Relevance Factors */}
            <div>
              <h4 className="font-medium mb-2">Relevance Factors</h4>
              <div className="space-y-2">
                {result.relevanceFactors.map((factor, index) => (
                  <div key={index} className="flex items-center justify-between p-2 bg-muted rounded">
                    <span className="text-sm">{factor.description}</span>
                    <div className="flex items-center gap-2">
                      <Progress value={factor.score * 100} className="w-16 h-2" />
                      <span className="text-xs font-medium w-10 text-right">
                        {Math.round(factor.score * 100)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </ScrollArea>

        <div className="flex items-center justify-between mt-4 pt-4 border-t">
          <div className="flex gap-2">
            <Button variant="outline" size="sm">
              <ExternalLink className="h-3 w-3 mr-1" />
              Open Full View
            </Button>
            <Button variant="outline" size="sm">
              <Share className="h-3 w-3 mr-1" />
              Share
            </Button>
          </div>
          <Button variant="default" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// Main Component
export const SearchResultsGrid: React.FC<SearchResultsGridProps> = ({
  results,
  totalResults,
  isLoading,
  hasNextPage = false,
  onLoadMore,
  onResultSelect,
  onResultPreview,
  onExportSelected,
  enableInfiniteScroll = true,
  enableVirtualization = true,
  itemsPerRow = 3,
  className
}) => {
  const [selectedResults, setSelectedResults] = useState<Set<string>>(new Set())
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [sortBy, setSortBy] = useState<'relevance' | 'date' | 'quality'>('relevance')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [previewResult, setPreviewResult] = useState<SearchResult | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  
  const gridRef = useRef<any>(null)

  // Sort results
  const sortedResults = useMemo(() => {
    const sorted = [...results]
    
    sorted.sort((a, b) => {
      const multiplier = sortOrder === 'asc' ? 1 : -1
      
      switch (sortBy) {
        case 'relevance':
          return (a.score - b.score) * multiplier
        case 'date':
          return (new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()) * multiplier
        case 'quality':
          return ((a.metadata.qualityScore || 0) - (b.metadata.qualityScore || 0)) * multiplier
        default:
          return 0
      }
    })
    
    return sorted
  }, [results, sortBy, sortOrder])

  // Calculate grid dimensions
  const itemHeight = viewMode === 'grid' ? 280 : 120
  const itemWidth = viewMode === 'grid' ? 300 : 800
  const actualItemsPerRow = viewMode === 'grid' ? itemsPerRow : 1
  const rowCount = Math.ceil(sortedResults.length / actualItemsPerRow)

  // Handle result selection
  const handleResultSelect = useCallback((resultId: string, selected: boolean) => {
    setSelectedResults(prev => {
      const newSet = new Set(prev)
      if (selected) {
        newSet.add(resultId)
      } else {
        newSet.delete(resultId)
      }
      return newSet
    })
    onResultSelect?.(resultId)
  }, [onResultSelect])

  // Handle result preview
  const handleResultPreview = useCallback((resultId: string) => {
    const result = sortedResults.find(r => r.id === resultId)
    if (result) {
      setPreviewResult(result)
      setShowPreview(true)
      onResultPreview?.(resultId)
    }
  }, [sortedResults, onResultPreview])

  // Handle select all
  const handleSelectAll = useCallback(() => {
    const allSelected = sortedResults.every(r => selectedResults.has(r.id))
    if (allSelected) {
      setSelectedResults(new Set())
    } else {
      setSelectedResults(new Set(sortedResults.map(r => r.id)))
    }
  }, [sortedResults, selectedResults])

  // Handle export selected
  const handleExportSelected = useCallback(() => {
    onExportSelected?.(Array.from(selectedResults))
  }, [selectedResults, onExportSelected])

  // Item data for virtualization
  const itemData = useMemo(() => ({
    results: sortedResults,
    itemsPerRow: actualItemsPerRow,
    selectedResults,
    onSelect: handleResultSelect,
    onPreview: handleResultPreview,
    viewMode
  }), [sortedResults, actualItemsPerRow, selectedResults, handleResultSelect, handleResultPreview, viewMode])

  // Infinite loading helper
  const isItemLoaded = useCallback((index: number) => {
    return !!sortedResults[index]
  }, [sortedResults])

  const loadMoreItems = useCallback(async () => {
    if (hasNextPage && onLoadMore) {
      await onLoadMore()
    }
  }, [hasNextPage, onLoadMore])

  return (
    <div className={cn('h-full flex flex-col', className)}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-medium">Search Results</h2>
          <Badge variant="outline">
            {totalResults.toLocaleString()} results
          </Badge>
          {selectedResults.size > 0 && (
            <Badge variant="default">
              {selectedResults.size} selected
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-2">
          {selectedResults.size > 0 && (
            <>
              <Button variant="outline" size="sm" onClick={handleExportSelected}>
                <Download className="h-3 w-3 mr-1" />
                Export ({selectedResults.size})
              </Button>
              <Separator orientation="vertical" className="h-4" />
            </>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={handleSelectAll}
            disabled={sortedResults.length === 0}
          >
            {sortedResults.every(r => selectedResults.has(r.id)) ? 'Deselect All' : 'Select All'}
          </Button>

          <Select value={sortBy} onValueChange={(value: any) => setSortBy(value)}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="relevance">Relevance</SelectItem>
              <SelectItem value="date">Date</SelectItem>
              <SelectItem value="quality">Quality</SelectItem>
            </SelectContent>
          </Select>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
          >
            <ArrowUpDown className={cn('h-3 w-3', sortOrder === 'desc' && 'rotate-180')} />
          </Button>

          <div className="flex items-center border rounded-md">
            <Button
              variant={viewMode === 'grid' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('grid')}
              className="rounded-r-none"
            >
              <Grid3X3 className="h-3 w-3" />
            </Button>
            <Button
              variant={viewMode === 'list' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => setViewMode('list')}
              className="rounded-l-none"
            >
              <List className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </div>

      {/* Results Grid */}
      <div className="flex-1 overflow-hidden">
        {isLoading && sortedResults.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent mx-auto mb-4" />
              <p className="text-sm text-muted-foreground">Searching...</p>
            </div>
          </div>
        ) : sortedResults.length > 0 ? (
          enableVirtualization && enableInfiniteScroll ? (
            <InfiniteLoader
              isItemLoaded={isItemLoaded}
              itemCount={hasNextPage ? sortedResults.length + 1 : sortedResults.length}
              loadMoreItems={loadMoreItems}
            >
              {({ onItemsRendered, ref }) => (
                <Grid
                  ref={(grid) => {
                    gridRef.current = grid
                    ref(grid)
                  }}
                  columnCount={actualItemsPerRow}
                  columnWidth={itemWidth}
                  height={600}
                  rowCount={rowCount}
                  rowHeight={itemHeight}
                  itemData={itemData}
                  onItemsRendered={({
                    visibleRowStartIndex,
                    visibleRowStopIndex,
                    overscanRowStopIndex
                  }) => {
                    onItemsRendered({
                      overscanStartIndex: visibleRowStartIndex * actualItemsPerRow,
                      overscanStopIndex: overscanRowStopIndex * actualItemsPerRow,
                      visibleStartIndex: visibleRowStartIndex * actualItemsPerRow,
                      visibleStopIndex: visibleRowStopIndex * actualItemsPerRow
                    })
                  }}
                  width="100%"
                >
                  {GridItem}
                </Grid>
              )}
            </InfiniteLoader>
          ) : (
            <ScrollArea className="h-full p-4">
              <div className={cn(
                viewMode === 'grid' 
                  ? 'grid gap-4'
                  : 'space-y-4',
                viewMode === 'grid' && 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4'
              )}>
                {sortedResults.map((result, index) => (
                  <GridItem
                    key={result.id}
                    columnIndex={viewMode === 'grid' ? index % actualItemsPerRow : 0}
                    rowIndex={viewMode === 'grid' ? Math.floor(index / actualItemsPerRow) : index}
                    style={{}}
                    data={itemData}
                  />
                ))}
              </div>
              
              {/* Load More Button */}
              {hasNextPage && !isLoading && (
                <div className="flex justify-center mt-6">
                  <Button variant="outline" onClick={loadMoreItems}>
                    Load More Results
                  </Button>
                </div>
              )}
              
              {/* Loading Indicator */}
              {isLoading && (
                <div className="flex justify-center mt-6">
                  <div className="flex items-center gap-2">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-accent" />
                    <span className="text-sm text-muted-foreground">Loading more...</span>
                  </div>
                </div>
              )}
            </ScrollArea>
          )
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Search className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <h3 className="text-lg font-medium mb-2">No Results Found</h3>
              <p className="text-sm text-muted-foreground">
                Try adjusting your search terms or filters
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Preview Modal */}
      <PreviewModal
        result={previewResult}
        isOpen={showPreview}
        onClose={() => {
          setShowPreview(false)
          setPreviewResult(null)
        }}
      />

      {/* Status Bar */}
      <div className="flex items-center justify-between p-2 border-t text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <span>
            Showing {sortedResults.length} of {totalResults.toLocaleString()} results
          </span>
          {selectedResults.size > 0 && (
            <span>{selectedResults.size} selected</span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <span>View: {viewMode}</span>
          <span>Sort: {sortBy} ({sortOrder})</span>
        </div>
      </div>
    </div>
  )
}

export default SearchResultsGrid