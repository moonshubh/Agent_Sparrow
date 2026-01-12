'use client';

import React, { useCallback } from 'react';
import { motion } from 'framer-motion';
import { ALL_ENTITY_TYPES, ENTITY_COLORS, ENTITY_LABELS, type EntityType } from '../types';

interface EntityTypeFilterProps {
  selected: EntityType[];
  onChange: (types: EntityType[]) => void;
}

export function EntityTypeFilter({ selected, onChange }: EntityTypeFilterProps) {
  const handleToggle = useCallback(
    (type: EntityType) => {
      if (selected.includes(type)) {
        onChange(selected.filter((t) => t !== type));
      } else {
        onChange([...selected, type]);
      }
    },
    [selected, onChange]
  );

  const handleSelectAll = useCallback(() => {
    // Align action with button label:
    // - When selected.length === 0: button shows "All Types" -> select all
    // - When selected.length > 0: button shows "Clear" -> clear all
    if (selected.length === 0) {
      onChange([...ALL_ENTITY_TYPES]);
    } else {
      onChange([]);
    }
  }, [selected.length, onChange]);

  return (
    <div className="entity-filter">
      <button
        className={`entity-filter-chip entity-filter-chip-all ${
          selected.length === 0 ? 'entity-filter-chip-active' : ''
        }`}
        onClick={handleSelectAll}
      >
        {selected.length === 0 ? 'All Types' : 'Clear'}
      </button>
      {ALL_ENTITY_TYPES.map((type) => {
        const isSelected = selected.includes(type);
        return (
          <motion.button
            key={type}
            className={`entity-filter-chip ${isSelected ? 'entity-filter-chip-active' : ''}`}
            onClick={() => handleToggle(type)}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            style={{
              borderColor: isSelected ? ENTITY_COLORS[type] : undefined,
              backgroundColor: isSelected ? `${ENTITY_COLORS[type]}20` : undefined,
            }}
          >
            <span
              className="entity-filter-dot"
              style={{ backgroundColor: ENTITY_COLORS[type] }}
            />
            <span>{ENTITY_LABELS[type]}</span>
          </motion.button>
        );
      })}
    </div>
  );
}
