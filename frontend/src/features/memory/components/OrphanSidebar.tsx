"use client";

import React, { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Layers, Search, X } from "lucide-react";
import { ENTITY_COLORS, ENTITY_LABELS } from "../types";
import type { OrphanEntity } from "../types";

export function OrphanSidebar({
  orphans,
  open,
  onToggle,
  onSelect,
}: {
  orphans: OrphanEntity[];
  open: boolean;
  onToggle: () => void;
  onSelect: (entityId: string) => void;
}) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return orphans;
    return orphans.filter((o) => {
      const name = o.node.entityName.toLowerCase();
      const label = o.node.displayLabel.toLowerCase();
      const type = o.node.entityType.toLowerCase();
      return (
        name.includes(trimmed) ||
        label.includes(trimmed) ||
        type.includes(trimmed)
      );
    });
  }, [orphans, query]);

  return (
    <motion.aside
      className={`orphan-sidebar ${open ? "open" : "collapsed"}`}
      initial={false}
      animate={{ width: open ? 280 : 44 }}
      transition={{ type: "spring", stiffness: 500, damping: 40 }}
    >
      <button
        className="orphan-sidebar__toggle"
        onClick={onToggle}
        title="Toggle disconnected entities"
      >
        <ChevronDown
          size={18}
          style={{ transform: open ? "rotate(90deg)" : "rotate(-90deg)" }}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            className="orphan-sidebar__content"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="orphan-sidebar__header">
              <div className="orphan-sidebar__title">
                <Layers size={16} />
                <span>Disconnected</span>
              </div>
              <div className="orphan-sidebar__count">{orphans.length}</div>
            </div>

            <div className="orphan-sidebar__hint">
              Entities not connected to the current tree root. Click one to jump
              and re-root the tree.
            </div>

            <div className="orphan-sidebar__search">
              <Search size={14} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search…"
              />
              {query && (
                <button
                  className="orphan-sidebar__clear"
                  onClick={() => setQuery("")}
                  title="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </div>

            <div className="orphan-sidebar__list" role="list">
              {filtered.length === 0 ? (
                <div className="orphan-sidebar__empty">No matches</div>
              ) : (
                filtered.map((o) => (
                  <button
                    key={o.id}
                    className="orphan-sidebar__item"
                    onClick={() => onSelect(o.id)}
                    title="Click to inspect"
                  >
                    <span
                      className="orphan-sidebar__dot"
                      style={{
                        backgroundColor: ENTITY_COLORS[o.node.entityType],
                      }}
                    />
                    <div className="orphan-sidebar__item-main">
                      <span className="orphan-sidebar__item-name">
                        {o.node.displayLabel}
                      </span>
                      <span className="orphan-sidebar__item-type">
                        {ENTITY_LABELS[o.node.entityType] ?? o.node.entityType}
                      </span>
                    </div>
                  </button>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.aside>
  );
}
