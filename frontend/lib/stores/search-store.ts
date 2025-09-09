/**
 * Search Store - Advanced Search Management
 * 
 * Handles search operations with proper API integration, advanced filtering,
 * search history, and performance analytics.
 */

import { create } from 'zustand'
import { devtools, subscribeWithSelector, persist } from 'zustand/middleware'
import { feedMeApi } from '@/lib/feedme-api'

// Types
export interface SearchFilters {
  dateRange: {
    from?: Date
    to?: Date
    preset?: 'all' | 'today' | 'week' | 'month' | 'year'
  }
  folders: number[]
  tags: string[]
  confidence: [number, number]
  platforms: string[]
  status: ('approved' | 'pending' | 'rejected')[]
  qualityScore: [number, number]
  issueTypes: string[]
  resolutionTypes: string[]
}

export interface SearchResult {
  id: number
  type: 'conversation'
  title: string
  snippet: string
  score: number
  conversation_id: number
  metadata: {
    folder_id?: number
    folder_name?: string
    tags: string[]
    confidence_score: number
    quality_score: number
    issue_type?: string
    resolution_type?: string
    created_at: string
    updated_at: string
  }
}

export interface SavedSearch {
  id: string
  name: string
  query: string
  filters: SearchFilters
  created_at: string
  last_used: string
  use_count: number
}

export interface SearchSuggestion {
  text: string
  type: 'recent' | 'popular' | 'autocomplete'
  frequency?: number
}

export interface SearchAnalytics {
  total_searches: number
  total_impressions: number
  total_clicks: number
  avg_response_time: number
  popular_queries: Array<{ query: string; count: number }>
  filter_usage: Record<string, number>
  result_click_through_rate: number
  zero_result_queries: string[]
}

interface SearchState {
  // Query State
  query: string
  filters: SearchFilters
  
  // Results State
  results: SearchResult[]
  totalResults: number
  currentPage: number
  pageSize: number
  hasMore: boolean
  
  // UI State
  isSearching: boolean
  lastSearchTime: number | null
  searchError: string | null
  
  // Search History
  searchHistory: string[]
  recentSearches: Array<{ query: string; timestamp: string; results_count: number }>
  suggestions: SearchSuggestion[]
  
  // Saved Searches
  savedSearches: SavedSearch[]
  
  // Analytics
  analytics: SearchAnalytics
  
  // Performance
  responseTime: number | null
  searchId: string | null
}

interface SearchActions {
  // Core Search
  performSearch: (query: string, options?: { 
    page?: number
    append?: boolean
    filters?: Partial<SearchFilters>
  }) => Promise<void>
  
  clearResults: () => void
  loadMore: () => Promise<void>
  
  // Query Management
  setQuery: (query: string) => void
  updateFilters: (filters: Partial<SearchFilters>) => void
  resetFilters: () => void
  
  // Search History
  addToHistory: (query: string, resultsCount: number) => void
  clearHistory: () => void
  removeFromHistory: (query: string) => void
  
  // Suggestions
  updateSuggestions: (query: string) => Promise<void>
  addSuggestion: (suggestion: SearchSuggestion) => void
  
  // Saved Searches
  saveSearch: (name: string, query?: string, filters?: SearchFilters) => void
  deleteSavedSearch: (id: string) => void
  loadSavedSearch: (id: string) => void
  updateSavedSearchUsage: (id: string) => void
  
  // Analytics
  recordSearchAnalytics: (query: string, responseTime: number, resultCount: number) => void
  recordResultClick: (resultId: number, position: number) => void
  getAnalytics: () => Promise<void>
  
  // Utilities
  exportResults: (format: 'csv' | 'json') => void
  getSearchUrl: () => string
  parseSearchUrl: (url: string) => void
}

export interface SearchStore extends SearchState {
  actions: SearchActions
}

// Default state
const DEFAULT_FILTERS: SearchFilters = {
  dateRange: { preset: 'all' },
  folders: [],
  tags: [],
  confidence: [0, 1],
  platforms: [],
  status: [],
  qualityScore: [0, 1],
  issueTypes: [],
  resolutionTypes: []
}

const DEFAULT_ANALYTICS: SearchAnalytics = {
  total_searches: 0,
  total_impressions: 0,
  total_clicks: 0,
  avg_response_time: 0,
  popular_queries: [],
  filter_usage: {},
  result_click_through_rate: 0,
  zero_result_queries: []
}

// Store Implementation
export const useSearchStore = create<SearchStore>()(
  devtools(
    subscribeWithSelector(
      persist(
        (set, get) => ({
          // Initial State
          query: '',
          filters: DEFAULT_FILTERS,
          results: [],
          totalResults: 0,
          currentPage: 1,
          pageSize: 20,
          hasMore: false,
          isSearching: false,
          lastSearchTime: null,
          searchError: null,
          searchHistory: [],
          recentSearches: [],
          suggestions: [],
          savedSearches: [],
          analytics: DEFAULT_ANALYTICS,
          responseTime: null,
          searchId: null,
          
          actions: {
            // ===========================
            // Core Search Operations
            // ===========================
            
            performSearch: async (query, options = {}) => {
              const state = get()
              const { page = 1, append = false, filters = {} } = options
              
              // Validate query
              if (!query.trim()) {
                set({ 
                  results: [],
                  totalResults: 0,
                  searchError: null
                })
                return
              }
              
              // Update search state
              const searchId = `search-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
              const startTime = Date.now()
              
              set({
                isSearching: true,
                searchError: null,
                searchId,
                currentPage: page,
                ...(page === 1 && !append ? { results: [] } : {})
              })
              
              try {
                // Unified text flow: example search removed; return no results for now
                const endTime = Date.now()
                const responseTime = endTime - startTime
                set(state => ({
                  isSearching: false,
                  results: append ? state.results : [],
                  totalResults: 0,
                  hasMore: false,
                  lastSearchTime: endTime,
                  responseTime,
                  searchError: null
                }))
                get().actions.recordSearchAnalytics(query, responseTime, 0)
                get().actions.addToHistory(query, 0)
                
              } catch (error) {
                console.error('Search failed:', error)
                
                const errorMessage = error instanceof Error ? error.message : 'Search failed'
                
                set({
                  isSearching: false,
                  searchError: errorMessage,
                  results: append ? get().results : []
                })
                
                // Record zero-result analytics
                get().actions.recordSearchAnalytics(query, Date.now() - startTime, 0)
              }
            },
            
            clearResults: () => {
              set({
                results: [],
                totalResults: 0,
                currentPage: 1,
                hasMore: false,
                searchError: null,
                responseTime: null,
                searchId: null
              })
            },
            
            loadMore: async () => {
              const state = get()
              
              if (!state.hasMore || state.isSearching || !state.query) {
                return
              }
              
              await state.actions.performSearch(state.query, {
                page: state.currentPage + 1,
                append: true
              })
            },
            
            // ===========================
            // Query Management
            // ===========================
            
            setQuery: (query) => {
              set({ query })
              
              // Update suggestions when query changes
              if (query.length > 2) {
                get().actions.updateSuggestions(query)
              }
            },
            
            updateFilters: (newFilters) => {
              set(state => ({
                filters: {
                  ...state.filters,
                  ...newFilters
                }
              }))
              
              // Re-run search if there's an active query
              const state = get()
              if (state.query) {
                state.actions.performSearch(state.query, { page: 1 })
              }
            },
            
            resetFilters: () => {
              set({ filters: DEFAULT_FILTERS })
              
              // Re-run search if there's an active query
              const state = get()
              if (state.query) {
                state.actions.performSearch(state.query, { page: 1 })
              }
            },
            
            // ===========================
            // Search History
            // ===========================
            
            addToHistory: (query, resultsCount) => {
              if (!query.trim()) return
              
              set(state => {
                const trimmedQuery = query.trim()
                
                // Remove if already exists
                const filteredHistory = state.searchHistory.filter(h => h !== trimmedQuery)
                const filteredRecent = state.recentSearches.filter(r => r.query !== trimmedQuery)
                
                return {
                  searchHistory: [trimmedQuery, ...filteredHistory].slice(0, 50),
                  recentSearches: [
                    {
                      query: trimmedQuery,
                      timestamp: new Date().toISOString(),
                      results_count: resultsCount
                    },
                    ...filteredRecent
                  ].slice(0, 20)
                }
              })
            },
            
            clearHistory: () => {
              set({
                searchHistory: [],
                recentSearches: []
              })
            },
            
            removeFromHistory: (query) => {
              set(state => ({
                searchHistory: state.searchHistory.filter(h => h !== query),
                recentSearches: state.recentSearches.filter(r => r.query !== query)
              }))
            },
            
            // ===========================
            // Suggestions
            // ===========================
            
            updateSuggestions: async (query) => {
              const state = get()
              
              // Get autocomplete suggestions
              const suggestions: SearchSuggestion[] = []
              
              // Add recent searches that match
              const recentMatches = state.searchHistory
                .filter(h => h.toLowerCase().includes(query.toLowerCase()))
                .slice(0, 5)
                .map(text => ({ text, type: 'recent' as const }))
              
              suggestions.push(...recentMatches)
              
              // Add popular queries that match
              const popularMatches = state.analytics.popular_queries
                .filter(p => p.query.toLowerCase().includes(query.toLowerCase()))
                .slice(0, 3)
                .map(p => ({ text: p.query, type: 'popular' as const, frequency: p.count }))
              
              suggestions.push(...popularMatches)
              
              // Could add API-based autocomplete here
              // try {
              //   const autocompleteResponse = await feedMeApi.getAutocompleteSuggestions(query)
              //   const autocompleteItems = autocompleteResponse.suggestions.map(s => ({
              //     text: s,
              //     type: 'autocomplete' as const
              //   }))
              //   suggestions.push(...autocompleteItems)
              // } catch (error) {
              //   console.warn('Autocomplete failed:', error)
              // }
              
              set({ suggestions })
            },
            
            addSuggestion: (suggestion) => {
              set(state => ({
                suggestions: [suggestion, ...state.suggestions.filter(s => s.text !== suggestion.text)].slice(0, 10)
              }))
            },
            
            // ===========================
            // Saved Searches
            // ===========================
            
            saveSearch: (name, query?, filters?) => {
              const state = get()
              
              const savedSearch: SavedSearch = {
                id: `saved-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
                name,
                query: query || state.query,
                filters: filters || state.filters,
                created_at: new Date().toISOString(),
                last_used: new Date().toISOString(),
                use_count: 1
              }
              
              set(state => ({
                savedSearches: [savedSearch, ...state.savedSearches]
              }))
            },
            
            deleteSavedSearch: (id) => {
              set(state => ({
                savedSearches: state.savedSearches.filter(s => s.id !== id)
              }))
            },
            
            loadSavedSearch: (id) => {
              const state = get()
              const savedSearch = state.savedSearches.find(s => s.id === id)
              
              if (savedSearch) {
                set({
                  query: savedSearch.query,
                  filters: savedSearch.filters
                })
                
                // Update usage
                state.actions.updateSavedSearchUsage(id)
                
                // Perform search
                state.actions.performSearch(savedSearch.query)
              }
            },
            
            updateSavedSearchUsage: (id) => {
              set(state => ({
                savedSearches: state.savedSearches.map(s => 
                  s.id === id 
                    ? { 
                        ...s, 
                        last_used: new Date().toISOString(),
                        use_count: s.use_count + 1 
                      }
                    : s
                )
              }))
            },
            
            // ===========================
            // Analytics
            // ===========================
            
            recordSearchAnalytics: (query, responseTime, resultCount) => {
              set(state => {
                const analytics = { ...state.analytics }
                
                analytics.total_searches++
                // Track impressions (results shown) only when results are returned
                if (resultCount > 0) {
                  analytics.total_impressions++
                }
                
                analytics.avg_response_time = (
                  (analytics.avg_response_time * (analytics.total_searches - 1) + responseTime) /
                  analytics.total_searches
                )
                
                // Update popular queries
                const existingQuery = analytics.popular_queries.find(p => p.query === query)
                if (existingQuery) {
                  existingQuery.count++
                } else {
                  analytics.popular_queries.push({ query, count: 1 })
                }
                
                // Sort and limit popular queries
                analytics.popular_queries = analytics.popular_queries
                  .sort((a, b) => b.count - a.count)
                  .slice(0, 20)
                
                // Track zero results
                if (resultCount === 0 && !analytics.zero_result_queries.includes(query)) {
                  analytics.zero_result_queries = [query, ...analytics.zero_result_queries].slice(0, 50)
                }
                
                return { analytics }
              })
            },
            
            recordResultClick: (resultId, position) => {
              set(state => {
                const analytics = { ...state.analytics }
                
                // Increment click count
                analytics.total_clicks++
                
                // Calculate click-through rate as clicks divided by impressions
                analytics.result_click_through_rate = analytics.total_impressions > 0
                  ? analytics.total_clicks / analytics.total_impressions
                  : 0
                
                return { analytics }
              })
            },
            
            getAnalytics: async () => {
              try {
                // TODO: Implement actual API call to retrieve analytics data
                // This is a placeholder implementation that will be replaced with:
                // const analyticsData = await feedMeApi.getSearchAnalytics()
                // set({ analytics: analyticsData })
                
                const state = get()
                console.log('Search analytics (placeholder):', state.analytics)
                
                // For now, just return the current analytics state
                return state.analytics
              } catch (error) {
                console.error('Failed to load search analytics:', error)
                throw error
              }
            },
            
            // ===========================
            // Utilities
            // ===========================
            
            exportResults: (format) => {
              const state = get()
              
              if (format === 'json') {
                const data = {
                  query: state.query,
                  filters: state.filters,
                  results: state.results,
                  total_results: state.totalResults,
                  exported_at: new Date().toISOString()
                }
                
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
                const url = URL.createObjectURL(blob)
                const link = document.createElement('a')
                link.href = url
                link.download = `feedme-search-results-${Date.now()}.json`
                link.click()
                URL.revokeObjectURL(url)
                
              } else if (format === 'csv') {
                const headers = ['ID', 'Type', 'Title', 'Score', 'Conversation ID', 'Folder', 'Tags', 'Created At']
                const rows = state.results.map(result => [
                  result.id,
                  result.type,
                  result.title,
                  result.score,
                  result.conversation_id,
                  result.metadata.folder_name || '',
                  result.metadata.tags.join('; '),
                  result.metadata.created_at
                ])
                
                const csvContent = [headers, ...rows]
                  .map(row => row.map(cell => `"${cell}"`).join(','))
                  .join('\n')
                
                const blob = new Blob([csvContent], { type: 'text/csv' })
                const url = URL.createObjectURL(blob)
                const link = document.createElement('a')
                link.href = url
                link.download = `feedme-search-results-${Date.now()}.csv`
                link.click()
                URL.revokeObjectURL(url)
              }
            },
            
            getSearchUrl: () => {
              const state = get()
              const params = new URLSearchParams()
              
              if (state.query) params.set('q', state.query)
              if (state.currentPage > 1) params.set('page', state.currentPage.toString())
              
              // Add filters to URL
              if (state.filters.folders.length > 0) {
                params.set('folders', state.filters.folders.join(','))
              }
              if (state.filters.tags.length > 0) {
                params.set('tags', state.filters.tags.join(','))
              }
              
              return params.toString() ? `?${params.toString()}` : ''
            },
            
            parseSearchUrl: (url) => {
              const params = new URLSearchParams(url)
              
              const query = params.get('q') || ''
              const page = parseInt(params.get('page') || '1')
              const folders = params.get('folders')?.split(',').map(Number) || []
              const tags = params.get('tags')?.split(',') || []
              
              set(state => ({
                query,
                currentPage: page,
                filters: {
                  ...state.filters,
                  folders,
                  tags
                }
              }))
              
              if (query) {
                get().actions.performSearch(query, { page })
              }
            }
          }
        }),
        {
          name: 'feedme-search-store',
          partialize: (state) => ({
            searchHistory: state.searchHistory,
            recentSearches: state.recentSearches,
            savedSearches: state.savedSearches,
            analytics: state.analytics
          })
        }
      )
    ),
    {
      name: 'feedme-search-store'
    }
  )
)

// Convenience hooks with individual selectors to avoid infinite loops
export const useSearch = () => {
  // Individual selectors to avoid object creation on every render
  const query = useSearchStore(state => state.query)
  const filters = useSearchStore(state => state.filters)
  const results = useSearchStore(state => state.results)
  const totalResults = useSearchStore(state => state.totalResults)
  const currentPage = useSearchStore(state => state.currentPage)
  const hasMore = useSearchStore(state => state.hasMore)
  const isSearching = useSearchStore(state => state.isSearching)
  const searchError = useSearchStore(state => state.searchError)
  const responseTime = useSearchStore(state => state.responseTime)

  return {
    query,
    filters,
    results,
    totalResults,
    currentPage,
    hasMore,
    isSearching,
    searchError,
    responseTime
  }
}

export const useSearchHistory = () => {
  // Individual selectors to avoid object creation on every render
  const searchHistory = useSearchStore(state => state.searchHistory)
  const recentSearches = useSearchStore(state => state.recentSearches)
  const suggestions = useSearchStore(state => state.suggestions)

  return {
    searchHistory,
    recentSearches,
    suggestions
  }
}

export const useSavedSearches = () => {
  // Individual selectors to avoid object creation on every render
  const savedSearches = useSearchStore(state => state.savedSearches)

  return {
    savedSearches
  }
}

export const useSearchAnalytics = () => {
  // Individual selectors to avoid object creation on every render
  const analytics = useSearchStore(state => state.analytics)

  return {
    analytics
  }
}

export const useSearchActions = () => useSearchStore(state => state.actions)
