/**
 * UnifiedSearchBar Component
 * 
 * Smart autocomplete with search suggestions, recent searches dropdown,
 * advanced filters toggle, and search analytics integration.
 * 
 * Part of FeedMe v2.0 Phase 3D: Advanced Search Interface
 */

'use client'

import React, { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { 
  Search, Filter, X, Clock, TrendingUp, Tag, 
  ChevronDown, ChevronUp, Settings, Save, History,
  FileText, MessageCircle, User, Calendar, Star,
  Zap, Target, Brain, ArrowRight
} from 'lucide-react'
import { useDebounce } from '@/hooks/use-debounce'
import { useSearch, useActions } from '@/lib/stores/feedme-store'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { DateRangePicker } from '@/components/ui/date-range-picker'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

// Types
interface UnifiedSearchBarProps {
  onSearch?: (query: string, filters: SearchFilters) => void
  onSuggestionSelect?: (suggestion: SearchSuggestion) => void
  onSaveSearch?: (name: string, query: string, filters: SearchFilters) => void
  enableAdvancedFilters?: boolean
  enableSuggestions?: boolean
  enableAnalytics?: boolean
  placeholder?: string
  className?: string
}

interface SearchFilters {
  dateRange: 'all' | 'today' | 'week' | 'month' | 'year' | 'custom'
  customDateRange?: { from: Date; to: Date }
  folders: number[]
  tags: string[]
  confidence: [number, number]
  platforms: string[]
  status: string[]
  qualityScore: [number, number]
  contentType: 'all' | 'conversations' | 'qa_pairs' | 'examples'
  sentiment: string[]
  priority: 'all' | 'high' | 'medium' | 'low'
  approvalStatus: 'all' | 'approved' | 'pending' | 'rejected'
}

interface SearchSuggestion {
  id: string
  type: 'query' | 'tag' | 'folder' | 'content' | 'smart'
  text: string
  description?: string
  category: string
  score: number
  metadata?: Record<string, any>
}

interface SearchAnalytics {
  popularQueries: string[]
  trendingTags: string[]
  searchVolume: number
  avgResponseTime: number
  successRate: number
}

// Search Suggestion Item Component
const SearchSuggestionItem: React.FC<{
  suggestion: SearchSuggestion
  isSelected: boolean
  onSelect: () => void
  onHover: () => void
}> = ({ suggestion, isSelected, onSelect, onHover }) => {
  const getSuggestionIcon = (type: SearchSuggestion['type']) => {
    switch (type) {
      case 'query': return <Search className="h-3 w-3" />
      case 'tag': return <Tag className="h-3 w-3" />
      case 'folder': return <FileText className="h-3 w-3" />
      case 'content': return <MessageCircle className="h-3 w-3" />
      case 'smart': return <Brain className="h-3 w-3" />
    }
  }

  const getSuggestionTypeColor = (type: SearchSuggestion['type']) => {
    switch (type) {
      case 'query': return 'text-blue-600'
      case 'tag': return 'text-green-600'
      case 'folder': return 'text-purple-600'
      case 'content': return 'text-orange-600'
      case 'smart': return 'text-pink-600'
    }
  }

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-2 cursor-pointer rounded-sm transition-colors',
        isSelected ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
      )}
      onClick={onSelect}
      onMouseEnter={onHover}
    >
      <div className={cn('flex-shrink-0', getSuggestionTypeColor(suggestion.type))}>
        {getSuggestionIcon(suggestion.type)}
      </div>
      
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium truncate">{suggestion.text}</div>
        {suggestion.description && (
          <div className="text-xs text-muted-foreground truncate">
            {suggestion.description}
          </div>
        )}
      </div>
      
      <div className="flex items-center gap-2 flex-shrink-0">
        <Badge variant="secondary" className="text-xs">
          {suggestion.category}
        </Badge>
        {suggestion.score > 0.8 && (
          <Star className="h-3 w-3 text-yellow-500" />
        )}
      </div>
    </div>
  )
}

// Advanced Filters Panel
const AdvancedFiltersPanel: React.FC<{
  filters: SearchFilters
  onFiltersChange: (filters: Partial<SearchFilters>) => void
  onReset: () => void
  onSave: () => void
}> = ({ filters, onFiltersChange, onReset, onSave }) => {
  const availableTags = ['sync', 'email', 'settings', 'loading', 'connectivity', 'troubleshooting']
  const availablePlatforms = ['zendesk', 'intercom', 'freshdesk', 'helpscout', 'custom']
  const availableStatuses = ['completed', 'processing', 'failed', 'pending']
  const availableSentiments = ['positive', 'neutral', 'negative']

  return (
    <Card className="absolute top-full left-0 right-0 mt-1 z-50 shadow-lg">
      <CardContent className="p-4 space-y-4">
        {/* Quick Filters */}
        <div>
          <Label className="text-sm font-medium mb-2 block">Quick Filters</Label>
          <div className="flex gap-2 flex-wrap">
            <Button
              variant={filters.dateRange === 'today' ? 'default' : 'outline'}
              size="sm"
              onClick={() => onFiltersChange({ dateRange: 'today' })}
            >
              Today
            </Button>
            <Button
              variant={filters.dateRange === 'week' ? 'default' : 'outline'}
              size="sm"
              onClick={() => onFiltersChange({ dateRange: 'week' })}
            >
              This Week
            </Button>
            <Button
              variant={filters.dateRange === 'month' ? 'default' : 'outline'}
              size="sm"
              onClick={() => onFiltersChange({ dateRange: 'month' })}
            >
              This Month
            </Button>
            <Button
              variant={filters.approvalStatus === 'approved' ? 'default' : 'outline'}
              size="sm"
              onClick={() => onFiltersChange({ 
                approvalStatus: filters.approvalStatus === 'approved' ? 'all' : 'approved' 
              })}
            >
              Approved Only
            </Button>
          </div>
        </div>

        <Separator />

        {/* Content Type */}
        <div>
          <Label className="text-sm font-medium mb-2 block">Content Type</Label>
          <Select 
            value={filters.contentType} 
            onValueChange={(value: SearchFilters['contentType']) => onFiltersChange({ contentType: value })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Content</SelectItem>
              <SelectItem value="conversations">Conversations</SelectItem>
              <SelectItem value="qa_pairs">Q&A Pairs</SelectItem>
              <SelectItem value="examples">Examples</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Tags */}
        <div>
          <Label className="text-sm font-medium mb-2 block">Tags</Label>
          <div className="flex gap-1 flex-wrap">
            {availableTags.map(tag => (
              <Button
                key={tag}
                variant={filters.tags.includes(tag) ? 'default' : 'outline'}
                size="sm"
                onClick={() => {
                  const newTags = filters.tags.includes(tag)
                    ? filters.tags.filter(t => t !== tag)
                    : [...filters.tags, tag]
                  onFiltersChange({ tags: newTags })
                }}
                className="text-xs"
              >
                {tag}
              </Button>
            ))}
          </div>
        </div>

        {/* Platforms */}
        <div>
          <Label className="text-sm font-medium mb-2 block">Platforms</Label>
          <div className="flex gap-1 flex-wrap">
            {availablePlatforms.map(platform => (
              <Button
                key={platform}
                variant={filters.platforms.includes(platform) ? 'default' : 'outline'}
                size="sm"
                onClick={() => {
                  const newPlatforms = filters.platforms.includes(platform)
                    ? filters.platforms.filter(p => p !== platform)
                    : [...filters.platforms, platform]
                  onFiltersChange({ platforms: newPlatforms })
                }}
                className="text-xs capitalize"
              >
                {platform}
              </Button>
            ))}
          </div>
        </div>

        {/* Status */}
        <div>
          <Label className="text-sm font-medium mb-2 block">Status</Label>
          <div className="flex gap-1 flex-wrap">
            {availableStatuses.map(status => (
              <Button
                key={status}
                variant={filters.status.includes(status) ? 'default' : 'outline'}
                size="sm"
                onClick={() => {
                  const newStatus = filters.status.includes(status)
                    ? filters.status.filter(s => s !== status)
                    : [...filters.status, status]
                  onFiltersChange({ status: newStatus })
                }}
                className="text-xs capitalize"
              >
                {status}
              </Button>
            ))}
          </div>
        </div>

        {/* Confidence Range */}
        <div>
          <Label className="text-sm font-medium mb-2 block">
            Confidence Range: {Math.round(filters.confidence[0] * 100)}% - {Math.round(filters.confidence[1] * 100)}%
          </Label>
          <Slider
            value={filters.confidence}
            onValueChange={(value) => onFiltersChange({ confidence: value as [number, number] })}
            max={1}
            min={0}
            step={0.05}
            className="w-full"
          />
        </div>

        {/* Quality Score Range */}
        <div>
          <Label className="text-sm font-medium mb-2 block">
            Quality Score: {Math.round(filters.qualityScore[0] * 100)}% - {Math.round(filters.qualityScore[1] * 100)}%
          </Label>
          <Slider
            value={filters.qualityScore}
            onValueChange={(value) => onFiltersChange({ qualityScore: value as [number, number] })}
            max={1}
            min={0}
            step={0.05}
            className="w-full"
          />
        </div>

        {/* Sentiment */}
        <div>
          <Label className="text-sm font-medium mb-2 block">Sentiment</Label>
          <div className="flex gap-1">
            {availableSentiments.map(sentiment => (
              <Button
                key={sentiment}
                variant={filters.sentiment.includes(sentiment) ? 'default' : 'outline'}
                size="sm"
                onClick={() => {
                  const newSentiment = filters.sentiment.includes(sentiment)
                    ? filters.sentiment.filter(s => s !== sentiment)
                    : [...filters.sentiment, sentiment]
                  onFiltersChange({ sentiment: newSentiment })
                }}
                className="text-xs capitalize"
              >
                {sentiment}
              </Button>
            ))}
          </div>
        </div>

        {/* Priority */}
        <div>
          <Label className="text-sm font-medium mb-2 block">Priority</Label>
          <Select 
            value={filters.priority} 
            onValueChange={(value: SearchFilters['priority']) => onFiltersChange({ priority: value })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Priorities</SelectItem>
              <SelectItem value="high">High Priority</SelectItem>
              <SelectItem value="medium">Medium Priority</SelectItem>
              <SelectItem value="low">Low Priority</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Approval Status */}
        <div>
          <Label className="text-sm font-medium mb-2 block">Approval Status</Label>
          <Select 
            value={filters.approvalStatus} 
            onValueChange={(value: SearchFilters['approvalStatus']) => onFiltersChange({ approvalStatus: value })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Separator />

        {/* Actions */}
        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={onReset}>
            Reset Filters
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onSave}>
              <Save className="h-3 w-3 mr-1" />
              Save Search
            </Button>
            <Button size="sm">Apply Filters</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Recent Searches Panel
const RecentSearchesPanel: React.FC<{
  searches: string[]
  savedSearches: Array<{ id: string; name: string; query: string }>
  onSelectSearch: (query: string) => void
  onSelectSaved: (search: { id: string; name: string; query: string }) => void
  onClearHistory: () => void
}> = ({ searches, savedSearches, onSelectSearch, onSelectSaved, onClearHistory }) => {
  return (
    <Card className="absolute top-full left-0 right-0 mt-1 z-50 shadow-lg">
      <CardContent className="p-0">
        <div className="max-h-80 overflow-hidden">
          {/* Recent Searches */}
          {searches.length > 0 && (
            <div>
              <div className="flex items-center justify-between p-3 border-b">
                <div className="flex items-center gap-2">
                  <History className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm font-medium">Recent Searches</span>
                </div>
                <Button variant="ghost" size="sm" onClick={onClearHistory}>
                  <X className="h-3 w-3" />
                </Button>
              </div>
              <ScrollArea className="max-h-32">
                {searches.map((search, index) => (
                  <div
                    key={index}
                    className="flex items-center gap-2 p-2 hover:bg-accent cursor-pointer"
                    onClick={() => onSelectSearch(search)}
                  >
                    <Clock className="h-3 w-3 text-muted-foreground" />
                    <span className="text-sm truncate">{search}</span>
                  </div>
                ))}
              </ScrollArea>
            </div>
          )}

          {/* Saved Searches */}
          {savedSearches.length > 0 && (
            <div>
              <div className="flex items-center gap-2 p-3 border-b">
                <Star className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Saved Searches</span>
              </div>
              <ScrollArea className="max-h-32">
                {savedSearches.map((saved) => (
                  <div
                    key={saved.id}
                    className="flex items-center gap-2 p-2 hover:bg-accent cursor-pointer"
                    onClick={() => onSelectSaved(saved)}
                  >
                    <Star className="h-3 w-3 text-yellow-500" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">{saved.name}</div>
                      <div className="text-xs text-muted-foreground truncate">{saved.query}</div>
                    </div>
                  </div>
                ))}
              </ScrollArea>
            </div>
          )}

          {/* Empty State */}
          {searches.length === 0 && savedSearches.length === 0 && (
            <div className="p-6 text-center">
              <Search className="h-8 w-8 mx-auto mb-2 text-muted-foreground opacity-50" />
              <p className="text-sm text-muted-foreground">No search history yet</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// Search Analytics Panel
const SearchAnalyticsPanel: React.FC<{
  analytics: SearchAnalytics
  onClose: () => void
}> = ({ analytics, onClose }) => {
  return (
    <Card className="absolute top-full right-0 mt-1 z-50 shadow-lg w-80">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-medium text-sm flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Search Analytics
          </h3>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-3 w-3" />
          </Button>
        </div>

        <div className="space-y-3">
          {/* Key Metrics */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-muted-foreground">Search Volume</div>
              <div className="font-medium">{analytics.searchVolume.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Success Rate</div>
              <div className="font-medium">{Math.round(analytics.successRate * 100)}%</div>
            </div>
            <div>
              <div className="text-muted-foreground">Avg Response</div>
              <div className="font-medium">{analytics.avgResponseTime}ms</div>
            </div>
            <div>
              <div className="text-muted-foreground">Trending Now</div>
              <div className="font-medium">{analytics.trendingTags.length} tags</div>
            </div>
          </div>

          <Separator />

          {/* Popular Queries */}
          <div>
            <h4 className="text-sm font-medium mb-2">Popular Queries</h4>
            <div className="space-y-1">
              {analytics.popularQueries.slice(0, 3).map((query, index) => (
                <div key={index} className="flex items-center gap-2 text-xs">
                  <span className="w-4 text-muted-foreground">{index + 1}.</span>
                  <span className="truncate">{query}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Trending Tags */}
          <div>
            <h4 className="text-sm font-medium mb-2">Trending Tags</h4>
            <div className="flex gap-1 flex-wrap">
              {analytics.trendingTags.slice(0, 5).map(tag => (
                <Badge key={tag} variant="secondary" className="text-xs">
                  {tag}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Main Component
export const UnifiedSearchBar: React.FC<UnifiedSearchBarProps> = ({
  onSearch,
  onSuggestionSelect,
  onSaveSearch,
  enableAdvancedFilters = true,
  enableSuggestions = true,
  enableAnalytics = true,
  placeholder = "Search conversations, Q&A pairs, and examples...",
  className
}) => {
  const { query, filters, searchHistory, savedSearches } = useSearch()
  const { performSearch, updateSearchFilters, addToSearchHistory, saveSearch, loadSavedSearch } = useActions()

  const [localQuery, setLocalQuery] = useState(query)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [showAnalytics, setShowAnalytics] = useState(false)
  const [selectedSuggestion, setSelectedSuggestion] = useState(-1)
  const [isSearching, setIsSearching] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)
  const debouncedQuery = useDebounce(localQuery, 300)

  // Mock suggestions
  const suggestions = useMemo<SearchSuggestion[]>(() => {
    if (!debouncedQuery.trim() || !enableSuggestions) return []

    const mockSuggestions: SearchSuggestion[] = [
      {
        id: 'smart-1',
        type: 'smart',
        text: `${debouncedQuery} issues`,
        description: 'AI-powered smart search for related issues',
        category: 'Smart',
        score: 0.95
      },
      {
        id: 'query-1',
        type: 'query',
        text: `${debouncedQuery} troubleshooting`,
        description: 'Search for troubleshooting guides',
        category: 'Query',
        score: 0.85
      },
      {
        id: 'tag-1',
        type: 'tag',
        text: debouncedQuery,
        description: 'Search by tag',
        category: 'Tag',
        score: 0.75
      },
      {
        id: 'content-1',
        type: 'content',
        text: `"${debouncedQuery}"`,
        description: 'Exact phrase match in content',
        category: 'Content',
        score: 0.80
      }
    ]

    return mockSuggestions.filter(s => 
      s.text.toLowerCase().includes(debouncedQuery.toLowerCase())
    )
  }, [debouncedQuery, enableSuggestions])

  // Mock analytics
  const mockAnalytics: SearchAnalytics = {
    popularQueries: ['email sync issues', 'mailbird settings', 'account setup'],
    trendingTags: ['sync', 'settings', 'troubleshooting', 'email', 'connectivity'],
    searchVolume: 1547,
    avgResponseTime: 125,
    successRate: 0.92
  }

  // Handle search submission
  const handleSearch = useCallback(async (searchQuery?: string, searchFilters?: SearchFilters) => {
    const finalQuery = searchQuery || localQuery
    const finalFilters = searchFilters || filters

    if (!finalQuery.trim()) return

    setIsSearching(true)
    setShowSuggestions(false)
    setShowHistory(false)

    try {
      await performSearch(finalQuery, finalFilters)
      addToSearchHistory(finalQuery)
      onSearch?.(finalQuery, finalFilters)
    } catch (error) {
      console.error('Search failed:', error)
    } finally {
      setIsSearching(false)
    }
  }, [localQuery, filters, performSearch, addToSearchHistory, onSearch])

  // Handle suggestion selection
  const handleSuggestionSelect = useCallback((suggestion: SearchSuggestion) => {
    setLocalQuery(suggestion.text)
    setShowSuggestions(false)
    handleSearch(suggestion.text)
    onSuggestionSelect?.(suggestion)
  }, [handleSearch, onSuggestionSelect])

  // Handle filter changes
  const handleFiltersChange = useCallback((newFilters: Partial<SearchFilters>) => {
    const updatedFilters = { ...filters, ...newFilters }
    updateSearchFilters(updatedFilters)
    
    if (localQuery.trim()) {
      handleSearch(localQuery, updatedFilters)
    }
  }, [filters, updateSearchFilters, localQuery, handleSearch])

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (showSuggestions && suggestions.length > 0) {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedSuggestion(prev => 
            prev < suggestions.length - 1 ? prev + 1 : 0
          )
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedSuggestion(prev => 
            prev > 0 ? prev - 1 : suggestions.length - 1
          )
          break
        case 'Enter':
          e.preventDefault()
          if (selectedSuggestion >= 0) {
            handleSuggestionSelect(suggestions[selectedSuggestion])
          } else {
            handleSearch()
          }
          break
        case 'Escape':
          setShowSuggestions(false)
          setSelectedSuggestion(-1)
          break
      }
    } else if (e.key === 'Enter') {
      handleSearch()
    }
  }, [showSuggestions, suggestions, selectedSuggestion, handleSuggestionSelect, handleSearch])

  // Handle input focus
  const handleInputFocus = useCallback(() => {
    if (enableSuggestions && localQuery.trim()) {
      setShowSuggestions(true)
    } else if (searchHistory.length > 0 || savedSearches.length > 0) {
      setShowHistory(true)
    }
  }, [enableSuggestions, localQuery, searchHistory.length, savedSearches.length])

  // Handle input blur
  const handleInputBlur = useCallback(() => {
    // Delay hiding to allow for suggestion clicks
    setTimeout(() => {
      setShowSuggestions(false)
      setShowHistory(false)
      setSelectedSuggestion(-1)
    }, 150)
  }, [])

  // Clear search
  const handleClear = useCallback(() => {
    setLocalQuery('')
    setShowSuggestions(false)
    setShowHistory(false)
    inputRef.current?.focus()
  }, [])

  // Handle saved search selection
  const handleSavedSearchSelect = useCallback((saved: { id: string; name: string; query: string }) => {
    loadSavedSearch(saved.id)
    setLocalQuery(saved.query)
    setShowHistory(false)
    handleSearch(saved.query)
  }, [loadSavedSearch, handleSearch])

  // Save current search
  const handleSaveCurrentSearch = useCallback(() => {
    if (localQuery.trim()) {
      const name = prompt('Enter a name for this search:')
      if (name) {
        saveSearch(name)
        onSaveSearch?.(name, localQuery, filters)
      }
    }
  }, [localQuery, filters, saveSearch, onSaveSearch])

  // Reset filters
  const handleResetFilters = useCallback(() => {
    const defaultFilters: SearchFilters = {
      dateRange: 'all',
      folders: [],
      tags: [],
      confidence: [0.0, 1.0],
      platforms: [],
      status: [],
      qualityScore: [0.0, 1.0],
      contentType: 'all',
      sentiment: [],
      priority: 'all',
      approvalStatus: 'all'
    }
    updateSearchFilters(defaultFilters)
  }, [updateSearchFilters])

  // Count active filters
  const activeFiltersCount = useMemo(() => {
    let count = 0
    if (filters.dateRange !== 'all') count++
    if (filters.folders.length > 0) count++
    if (filters.tags.length > 0) count++
    if (filters.confidence[0] > 0 || filters.confidence[1] < 1) count++
    if (filters.platforms.length > 0) count++
    if (filters.status.length > 0) count++
    if (filters.qualityScore[0] > 0 || filters.qualityScore[1] < 1) count++
    if (filters.contentType !== 'all') count++
    if (filters.sentiment.length > 0) count++
    if (filters.priority !== 'all') count++
    if (filters.approvalStatus !== 'all') count++
    return count
  }, [filters])

  return (
    <div className={cn('relative w-full', className)}>
      {/* Main Search Input */}
      <div className="relative">
        <div className="relative flex items-center">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          
          <Input
            ref={inputRef}
            type="text"
            placeholder={placeholder}
            value={localQuery}
            onChange={(e) => setLocalQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={handleInputFocus}
            onBlur={handleInputBlur}
            className="pl-10 pr-20"
            disabled={isSearching}
          />

          <div className="absolute right-2 top-1/2 transform -translate-y-1/2 flex items-center gap-1">
            {localQuery && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClear}
                className="h-6 w-6 p-0"
              >
                <X className="h-3 w-3" />
              </Button>
            )}

            {enableAdvancedFilters && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowFilters(!showFilters)}
                      className={cn(
                        'h-6 w-6 p-0',
                        (showFilters || activeFiltersCount > 0) && 'text-accent-foreground bg-accent'
                      )}
                    >
                      <Filter className="h-3 w-3" />
                      {activeFiltersCount > 0 && (
                        <Badge variant="secondary" className="absolute -top-1 -right-1 h-4 w-4 p-0 text-xs">
                          {activeFiltersCount}
                        </Badge>
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Advanced Filters {activeFiltersCount > 0 && `(${activeFiltersCount} active)`}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}

            {enableAnalytics && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowAnalytics(!showAnalytics)}
                      className="h-6 w-6 p-0"
                    >
                      <TrendingUp className="h-3 w-3" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Search Analytics</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </div>
        </div>

        {/* Loading Indicator */}
        {isSearching && (
          <div className="absolute top-full left-0 right-0 mt-1">
            <div className="flex items-center gap-2 p-2 bg-muted rounded text-sm">
              <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-accent" />
              Searching...
            </div>
          </div>
        )}
      </div>

      {/* Search Suggestions */}
      {showSuggestions && suggestions.length > 0 && !isSearching && (
        <Card className="absolute top-full left-0 right-0 mt-1 z-50 shadow-lg">
          <CardContent className="p-0">
            <ScrollArea className="max-h-80">
              {suggestions.map((suggestion, index) => (
                <SearchSuggestionItem
                  key={suggestion.id}
                  suggestion={suggestion}
                  isSelected={index === selectedSuggestion}
                  onSelect={() => handleSuggestionSelect(suggestion)}
                  onHover={() => setSelectedSuggestion(index)}
                />
              ))}
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {/* Recent Searches */}
      {showHistory && !showSuggestions && !isSearching && (
        <RecentSearchesPanel
          searches={searchHistory}
          savedSearches={savedSearches}
          onSelectSearch={(search) => {
            setLocalQuery(search)
            setShowHistory(false)
            handleSearch(search)
          }}
          onSelectSaved={handleSavedSearchSelect}
          onClearHistory={() => {
            // Clear search history
            setShowHistory(false)
          }}
        />
      )}

      {/* Advanced Filters */}
      {showFilters && enableAdvancedFilters && (
        <AdvancedFiltersPanel
          filters={filters}
          onFiltersChange={handleFiltersChange}
          onReset={handleResetFilters}
          onSave={handleSaveCurrentSearch}
        />
      )}

      {/* Search Analytics */}
      {showAnalytics && enableAnalytics && (
        <SearchAnalyticsPanel
          analytics={mockAnalytics}
          onClose={() => setShowAnalytics(false)}
        />
      )}

      {/* Quick Actions Bar */}
      {(localQuery.trim() || activeFiltersCount > 0) && (
        <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
          <span>Quick actions:</span>
          
          {localQuery.trim() && (
            <Button variant="ghost" size="sm" onClick={handleSaveCurrentSearch} className="h-6 px-2">
              <Save className="h-3 w-3 mr-1" />
              Save
            </Button>
          )}
          
          {activeFiltersCount > 0 && (
            <Button variant="ghost" size="sm" onClick={handleResetFilters} className="h-6 px-2">
              <X className="h-3 w-3 mr-1" />
              Clear {activeFiltersCount} filter{activeFiltersCount === 1 ? '' : 's'}
            </Button>
          )}
          
          <Button variant="ghost" size="sm" onClick={() => handleSearch()} className="h-6 px-2">
            <Search className="h-3 w-3 mr-1" />
            Search
          </Button>
        </div>
      )}
    </div>
  )
}

export default UnifiedSearchBar