'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Search, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useDebounce } from '@/shared/hooks/use-debounce';
import { TIMING } from '../lib/api';

interface MemorySearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function MemorySearch({ value, onChange, placeholder = 'Search...' }: MemorySearchProps) {
  const [inputValue, setInputValue] = useState(value);
  const debouncedValue = useDebounce(inputValue, TIMING.SEARCH_DEBOUNCE_MS);

  // Update parent when debounced value changes (only if different)
  useEffect(() => {
    // Only call onChange if the value is actually different to prevent loops
    if (debouncedValue !== value) {
      onChange(debouncedValue);
    }
  }, [debouncedValue, onChange, value]);

  // Sync with external value changes (only if different to prevent loops)
  useEffect(() => {
    if (value !== inputValue) {
      setInputValue(value);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]); // Intentionally exclude inputValue to prevent infinite loops

  const handleClear = useCallback(() => {
    setInputValue('');
    onChange('');
  }, [onChange]);

  return (
    <div className="memory-search">
      <div className="memory-search-icon">
        <Search size={16} />
      </div>
      <input
        type="text"
        className="memory-search-input"
        placeholder={placeholder}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        aria-label="Search memories"
      />
      <AnimatePresence>
        {inputValue && (
          <motion.button
            className="memory-search-clear"
            type="button"
            onClick={handleClear}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            aria-label="Clear search"
          >
            <X size={14} />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
