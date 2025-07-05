/**
 * Example: Search Component with Advanced Filters using Modular Stores
 * 
 * Demonstrates how to use the search store with its advanced filtering
 * capabilities and real API integration.
 */

'use client'

import React, { useState, useCallback } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Slider } from '@/components/ui/slider'
import { Calendar } from '@/components/ui/calendar'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Search, Filter, Calendar as CalendarIcon, Loader2 } from 'lucide-react'
import { format } from 'date-fns'

// Import specific search store hooks - NO legacy imports
import {
  useSearch,
  useSearchActions,
  useSearchHistory,
  useSavedSearches
} from '@/lib/stores/search-store'
import { useUIActions } from '@/lib/stores/ui-store'

export function SearchWithFiltersExample() {
  const { query, filters, results, isSearching, totalResults } = useSearch()
  const searchActions = useSearchActions()
  const searchHistory = useSearchHistory()
  const savedSearches = useSavedSearches()
  const uiActions = useUIActions()

  const [showFilters, setShowFilters] = useState(false)
  const [localQuery, setLocalQuery] = useState(query)

  // Handle search with debouncing built into the store
  const handleSearch = useCallback(() => {
    if (localQuery.trim()) {
      searchActions.performSearch(localQuery.trim())
    }
  }, [localQuery, searchActions])

  // Handle filter changes
  const handleConfidenceChange = (value: number[]) => {
    searchActions.updateFilters({
      confidence: [value[0], value[1]]
    })
  }

  const handleDateChange = (date: Date | undefined, type: 'from' | 'to') => {
    searchActions.updateFilters({
      dateRange: {
        ...filters.dateRange,
        [type]: date
      }
    })
  }

  const handleSaveSearch = () => {
    if (query && results.length > 0) {
      searchActions.saveSearch(`Search: ${query}`, query, filters)
      uiActions.showToast({
        type: 'success',
        title: 'Search Saved',
        message: 'Your search has been saved for future use'
      })
    }
  }

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={localQuery}
            onChange={(e) => setLocalQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search conversations..."
            className="pl-10"
          />
        </div>
        <Button onClick={handleSearch} disabled={isSearching}>
          {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
        </Button>
        <Button 
          variant="outline" 
          onClick={() => setShowFilters(!showFilters)}
        >
          <Filter className="h-4 w-4 mr-2" />
          Filters
        </Button>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <Card>
          <CardContent className="p-4 space-y-4">
            {/* Confidence Score Filter */}
            <div>
              <label className="text-sm font-medium">
                Confidence Score: {filters.confidence[0]}% - {filters.confidence[1]}%
              </label>
              <Slider
                value={filters.confidence}
                onValueChange={handleConfidenceChange}
                min={0}
                max={100}
                step={5}
                className="mt-2"
              />
            </div>

            {/* Date Range Filter */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium">From Date</label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="w-full justify-start">
                      <CalendarIcon className="mr-2 h-4 w-4" />
