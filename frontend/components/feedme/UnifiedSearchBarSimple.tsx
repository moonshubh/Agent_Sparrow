/**
 * UnifiedSearchBar - Simplified Version
 * Smart search with basic autocomplete functionality
 */

'use client'

import React, { useState, useCallback } from 'react'
import { Search, Filter } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useSearchActions } from '@/lib/stores/search-store'

interface UnifiedSearchBarProps {
  className?: string
  placeholder?: string
}

export function UnifiedSearchBar({ 
  className,
  placeholder = "Search conversations, examples..." 
}: UnifiedSearchBarProps) {
  const [query, setQuery] = useState('')
  const searchActions = useSearchActions()

  const handleSearch = useCallback(async () => {
    if (query.trim()) {
      await searchActions.performSearch(query)
    }
  }, [query, searchActions])

  const handleKeyPress = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }, [handleSearch])

  return (
    <div className={className}>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="text"
            placeholder={placeholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyPress={handleKeyPress}
            className="pl-10 ring-1 ring-accent/60 focus-visible:ring-accent"
          />
        </div>
        
        <Button 
          variant="outline" 
          size="sm"
          onClick={() => {
            // TODO: Implement filter functionality
            console.log('Filter functionality coming soon')
          }}
          title="Filter feature coming soon"
        >
          <Filter className="h-4 w-4" />
        </Button>
        
        <Button onClick={handleSearch} variant="default" size="sm">
          Search
        </Button>
      </div>
    </div>
  )
}