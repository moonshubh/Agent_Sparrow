'use client';

import React, { useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Layers, Search, X } from 'lucide-react';
import { ENTITY_COLORS, ENTITY_LABELS } from '../types';
import type { GraphNode } from '../types';

const DEFAULT_ENTITY_COLOR = '#94a3b8';

interface ChildrenPopoverProps {
  readonly open: boolean;
  readonly title: string;
  readonly childrenNodes: readonly GraphNode[];
  readonly onClose: () => void;
  readonly onSelectNode: (node: GraphNode) => void;
}

export function ChildrenPopover({
  open,
  title,
  childrenNodes,
  onClose,
  onSelectNode,
}: ChildrenPopoverProps) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return childrenNodes;
    return childrenNodes.filter((n) => {
      const name = n.entityName.toLowerCase();
      const label = n.displayLabel.toLowerCase();
      const type = n.entityType.toLowerCase();
      return (
        name.includes(trimmed) || label.includes(trimmed) || type.includes(trimmed)
      );
    });
  }, [childrenNodes, query]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="children-popover"
          initial={{ opacity: 0, y: 10, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.98 }}
          transition={{ type: 'spring', stiffness: 400, damping: 32 }}
        >
          <div className="children-popover__header">
            <div className="children-popover__title">
              <Layers size={16} />
              <span>{title}</span>
            </div>
            <button
              className="children-popover__close"
              type="button"
              onClick={onClose}
              title="Close"
            >
              <X size={16} />
            </button>
          </div>

          <div className="children-popover__search">
            <Search size={14} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search…"
              aria-label="Search child nodes"
            />
            {query && (
              <button
                className="children-popover__clear"
                type="button"
                onClick={() => setQuery('')}
                title="Clear search"
              >
                <X size={14} />
              </button>
            )}
          </div>

          <div className="children-popover__list">
            {filtered.length === 0 ? (
              <div className="children-popover__empty">No matches</div>
            ) : (
              filtered.map((child) => (
                <button
                  key={child.id}
                  className="children-popover__item"
                  type="button"
                  onClick={() => onSelectNode(child)}
                >
                  <span
                    className="children-popover__dot"
                    style={{
                      backgroundColor: ENTITY_COLORS[child.entityType] ?? DEFAULT_ENTITY_COLOR,
                    }}
                  />
                  <span className="children-popover__name">{child.displayLabel}</span>
                  <span className="children-popover__type">
                    {ENTITY_LABELS[child.entityType] ?? child.entityType}
                  </span>
                </button>
              ))
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
