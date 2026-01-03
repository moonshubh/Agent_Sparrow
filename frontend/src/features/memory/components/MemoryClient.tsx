'use client';

import React, { useMemo, useState, useCallback, Suspense } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ArrowLeft,
  ArrowDownToLine,
  Network,
  Table,
  GitMerge,
  SquarePen,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Brain,
  Search,
  TrendingUp,
  TrendingDown,
  Minus,
  Layers,
  Link2,
  AlertTriangle,
  Database,
  Sparkles,
} from 'lucide-react';
import { toast } from 'sonner';
import { useMemoryStats, useDuplicateCandidates, useImportMemorySources } from '../hooks';
import { MemorySearch } from './memory-search';
import { GraphErrorBoundary } from './GraphErrorBoundary';
import { ALL_ENTITY_TYPES, type EntityType, type MemoryFilters } from '../types';
import '../styles/memory.css';

// Lazy load heavy components
const MemoryGraph = React.lazy(() => import('./MemoryGraph'));
const MemoryTable = React.lazy(() => import('./MemoryTable'));
const DuplicateReview = React.lazy(() => import('./DuplicateReview'));
const MemoryForm = React.lazy(() =>
  import('./MemoryForm').then((module) => ({ default: module.MemoryForm }))
);

type ViewMode = 'graph' | 'table' | 'duplicates';

const defaultFilters: MemoryFilters = {
  searchQuery: '',
  entityTypes: [...ALL_ENTITY_TYPES],
  minConfidence: 0,
  sourceType: null,
  sortBy: 'created_at',
  sortOrder: 'desc',
};

// Navigation items configuration
const NAV_ITEMS = [
  { id: 'graph' as ViewMode, label: 'Graph View', icon: Network },
  { id: 'table' as ViewMode, label: 'Table View', icon: Table },
  { id: 'duplicates' as ViewMode, label: 'Duplicates', icon: GitMerge },
] as const;

// Spring animation config for smooth interactions
const springConfig = {
  type: 'spring' as const,
  stiffness: 500,
  damping: 35,
};

// Faster config for sidebar collapse - snappy feel
const sidebarSpring = {
  type: 'spring' as const,
  stiffness: 700,
  damping: 40,
};

export default function MemoryClient() {
  // View state
  const [viewMode, setViewMode] = useState<ViewMode>('graph');
  const [filters, setFilters] = useState<MemoryFilters>(defaultFilters);
  const [showAddForm, setShowAddForm] = useState(false);
  const [graphKey, setGraphKey] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [focusedMemoryId, setFocusedMemoryId] = useState<string | null>(null);
  const [relationshipReturn, setRelationshipReturn] = useState<
    { relationshipId: string; tab?: 'edit' | 'ai' | 'evidence' } | null
  >(null);
  const [pendingRelationshipOpen, setPendingRelationshipOpen] = useState<
    { relationshipId: string; tab?: 'edit' | 'ai' | 'evidence' } | null
  >(null);

  // Data hooks
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useMemoryStats();
  const { data: duplicates } = useDuplicateCandidates('pending');
  const importSources = useImportMemorySources();

  const availableEntityTypes = useMemo(() => {
    const counts = stats?.entity_types;
    if (!counts) return ALL_ENTITY_TYPES;
    return ALL_ENTITY_TYPES.filter((type) => (counts[type] ?? 0) > 0);
  }, [stats?.entity_types]);

  const effectiveEntityFilter = useMemo(() => {
    const availableSet = new Set(availableEntityTypes);
    return filters.entityTypes.filter((type) => availableSet.has(type));
  }, [availableEntityTypes, filters.entityTypes]);

  // Handlers
  const handleSearchChange = useCallback((query: string) => {
    setFilters((prev) => ({ ...prev, searchQuery: query }));
  }, []);

  const handleEntityTypeToggle = useCallback((type: EntityType) => {
    setFilters((prev) => {
      const current = prev.entityTypes;
      const updated = current.includes(type)
        ? current.filter((t) => t !== type)
        : [...current, type];
      return { ...prev, entityTypes: updated };
    });
  }, []);

  const handleSelectAllEntities = useCallback(() => {
    setFilters((prev) => ({ ...prev, entityTypes: [...availableEntityTypes] }));
  }, [availableEntityTypes]);

  const handleDeselectAllEntities = useCallback(() => {
    setFilters((prev) => ({ ...prev, entityTypes: [] }));
  }, []);

  const handleGraphErrorReset = useCallback(() => {
    setGraphKey((prev) => prev + 1);
  }, []);

  const handleRefresh = useCallback(() => {
    refetchStats();
  }, [refetchStats]);

  const handleInspectMemoryFromRelationship = useCallback(
    (memoryId: string, relationshipId: string) => {
      setFocusedMemoryId(memoryId);
      setRelationshipReturn({ relationshipId, tab: 'ai' });
      setViewMode('table');
    },
    []
  );

  const handleImportSources = useCallback(async () => {
    try {
      const result = await importSources.mutateAsync({
        include_issue_resolutions: true,
        include_playbook_entries: true,
        include_playbook_files: true,
        include_mem0_primary: true,
        limit: 200,
        include_playbook_embeddings: false,
      });

      toast.success(
        `Imported ${result.issue_resolutions_imported} issue patterns, ${result.playbook_entries_imported} playbook entries, ${result.playbook_files_imported} playbook files, and ${result.mem0_primary_imported} mem0 facts`
      );
      refetchStats();
      setGraphKey((prev) => prev + 1);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Import failed';
      toast.error(message);
    }
  }, [importSources, refetchStats]);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => !prev);
  }, []);

  const pendingDuplicatesCount = duplicates?.length || 0;

  return (
    <div className="memory-container">
      {/* Horizontal Layout Wrapper */}
      <div className="memory-layout">
        {/* Collapsible Sidebar */}
        <motion.aside
          className={`memory-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}
          initial={false}
          animate={{ width: sidebarCollapsed ? 72 : 280 }}
          transition={sidebarSpring}
        >
          {/* Sidebar Header */}
          <div className="memory-sidebar-header">
            <motion.div
              className="memory-sidebar-brand"
              animate={{ opacity: sidebarCollapsed ? 0 : 1 }}
              transition={{ duration: 0.15 }}
            >
              {!sidebarCollapsed && (
                <>
                  <Brain className="memory-sidebar-logo" size={24} />
                  <span className="memory-sidebar-title">Memory</span>
                </>
              )}
            </motion.div>
            <motion.button
              className="memory-sidebar-toggle"
              onClick={toggleSidebar}
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.95 }}
              aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {sidebarCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
            </motion.button>
          </div>

          {/* Sidebar Stats Section */}
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.div
                className="sidebar-stats"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
              >
                <div className="sidebar-stats-grid">
                  {/* Total Memories */}
                  <motion.div
                    className="sidebar-stat-card"
                    whileHover={{ scale: 1.02, y: -2 }}
                    transition={springConfig}
                  >
                    <div className="sidebar-stat-icon sidebar-stat-icon-primary">
                      <Database size={16} />
                    </div>
                    <div className="sidebar-stat-content">
                      <span className="sidebar-stat-value">
                        {statsLoading ? '—' : stats?.total_memories.toLocaleString() || '0'}
                      </span>
                      <span className="sidebar-stat-label">Memories</span>
                    </div>
                  </motion.div>

                  {/* Entities */}
                  <motion.div
                    className="sidebar-stat-card"
                    whileHover={{ scale: 1.02, y: -2 }}
                    transition={springConfig}
                  >
                    <div className="sidebar-stat-icon sidebar-stat-icon-blue">
                      <Layers size={16} />
                    </div>
                    <div className="sidebar-stat-content">
                      <span className="sidebar-stat-value">
                        {statsLoading ? '—' : stats?.total_entities.toLocaleString() || '0'}
                      </span>
                      <span className="sidebar-stat-label">Entities</span>
                    </div>
                  </motion.div>

                  {/* Relationships */}
                  <motion.div
                    className="sidebar-stat-card"
                    whileHover={{ scale: 1.02, y: -2 }}
                    transition={springConfig}
                  >
                    <div className="sidebar-stat-icon sidebar-stat-icon-green">
                      <Link2 size={16} />
                    </div>
                    <div className="sidebar-stat-content">
                      <span className="sidebar-stat-value">
                        {statsLoading ? '—' : stats?.total_relationships.toLocaleString() || '0'}
                      </span>
                      <span className="sidebar-stat-label">Relations</span>
                    </div>
                  </motion.div>

                  {/* Pending Duplicates */}
                  <motion.div
                    className={`sidebar-stat-card ${pendingDuplicatesCount > 0 ? 'has-alert' : ''}`}
                    whileHover={{ scale: 1.02, y: -2 }}
                    transition={springConfig}
                  >
                    <div className={`sidebar-stat-icon ${pendingDuplicatesCount > 0 ? 'sidebar-stat-icon-warning' : 'sidebar-stat-icon-gray'}`}>
                      <AlertTriangle size={16} />
                    </div>
                    <div className="sidebar-stat-content">
                      <span className="sidebar-stat-value">
                        {statsLoading ? '—' : pendingDuplicatesCount}
                      </span>
                      <span className="sidebar-stat-label">Duplicates</span>
                    </div>
                  </motion.div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Navigation Items */}
          <nav className="memory-sidebar-nav">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = viewMode === item.id;
              const hasBadge = item.id === 'duplicates' && pendingDuplicatesCount > 0;

              return (
                <motion.button
                  key={item.id}
                  className={`memory-nav-item ${isActive ? 'active' : ''}`}
                  onClick={() => setViewMode(item.id)}
                  whileHover={{ x: 4 }}
                  whileTap={{ scale: 0.98 }}
                  transition={springConfig}
                >
                  <motion.div
                    className="memory-nav-icon"
                    whileHover={{ rotate: isActive ? 0 : 5 }}
                    transition={springConfig}
                  >
                    <Icon size={20} />
                  </motion.div>
                  <AnimatePresence>
                    {!sidebarCollapsed && (
                      <motion.span
                        className="memory-nav-label"
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -10 }}
                        transition={{ duration: 0.15 }}
                      >
                        {item.label}
                      </motion.span>
                    )}
                  </AnimatePresence>
                  {hasBadge && (
                    <motion.span
                      className="memory-nav-badge"
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={springConfig}
                    >
                      {pendingDuplicatesCount}
                    </motion.span>
                  )}
                  {isActive && (
                    <motion.div
                      className="memory-nav-indicator"
                      layoutId="nav-indicator"
                      transition={springConfig}
                    />
                  )}
                </motion.button>
              );
            })}

          </nav>

          {/* Confidence Distribution - Sidebar Section */}
          <AnimatePresence>
            {!sidebarCollapsed && stats && (
              <motion.div
                className="sidebar-confidence"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.2 }}
              >
                <div className="sidebar-confidence-header">
                  <span className="sidebar-confidence-title">Confidence</span>
                  <span className="sidebar-confidence-percent">
                    {stats.total_memories > 0
                      ? Math.round((stats.high_confidence / stats.total_memories) * 100)
                      : 0}% high
                  </span>
                </div>
                <div className="sidebar-confidence-bars">
                  {/* High */}
                  <div className="sidebar-confidence-row">
                    <div className="sidebar-confidence-label">
                      <TrendingUp size={12} className="sidebar-icon-success" />
                      <span>High</span>
                    </div>
                    <div className="sidebar-confidence-track">
                      <motion.div
                        className="sidebar-confidence-fill sidebar-fill-success"
                        initial={{ width: 0 }}
                        animate={{
                          width: stats.total_memories > 0
                            ? `${(stats.high_confidence / stats.total_memories) * 100}%`
                            : '0%',
                        }}
                        transition={{ delay: 0.2, duration: 0.6 }}
                      />
                    </div>
                    <span className="sidebar-confidence-count">{stats.high_confidence}</span>
                  </div>
                  {/* Medium */}
                  <div className="sidebar-confidence-row">
                    <div className="sidebar-confidence-label">
                      <Minus size={12} className="sidebar-icon-warning" />
                      <span>Med</span>
                    </div>
                    <div className="sidebar-confidence-track">
                      <motion.div
                        className="sidebar-confidence-fill sidebar-fill-warning"
                        initial={{ width: 0 }}
                        animate={{
                          width: stats.total_memories > 0
                            ? `${(stats.medium_confidence / stats.total_memories) * 100}%`
                            : '0%',
                        }}
                        transition={{ delay: 0.3, duration: 0.6 }}
                      />
                    </div>
                    <span className="sidebar-confidence-count">{stats.medium_confidence}</span>
                  </div>
                  {/* Low */}
                  <div className="sidebar-confidence-row">
                    <div className="sidebar-confidence-label">
                      <TrendingDown size={12} className="sidebar-icon-danger" />
                      <span>Low</span>
                    </div>
                    <div className="sidebar-confidence-track">
                      <motion.div
                        className="sidebar-confidence-fill sidebar-fill-danger"
                        initial={{ width: 0 }}
                        animate={{
                          width: stats.total_memories > 0
                            ? `${(stats.low_confidence / stats.total_memories) * 100}%`
                            : '0%',
                        }}
                        transition={{ delay: 0.4, duration: 0.6 }}
                      />
                    </div>
                    <span className="sidebar-confidence-count">{stats.low_confidence}</span>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Sidebar Actions */}
          <div className="memory-sidebar-actions">
            <motion.button
              className="memory-sidebar-action"
              onClick={() => setShowAddForm(true)}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              transition={springConfig}
            >
              <SquarePen size={18} />
              <AnimatePresence>
                {!sidebarCollapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    Add Memory
                  </motion.span>
                )}
              </AnimatePresence>
            </motion.button>

            <motion.button
              className="memory-sidebar-action"
              onClick={handleImportSources}
              disabled={importSources.isPending}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              transition={springConfig}
              title="Backfill Memory UI from issue patterns + playbooks"
            >
              <ArrowDownToLine size={18} />
              <AnimatePresence>
                {!sidebarCollapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    {importSources.isPending ? 'Importing…' : 'Import Knowledge'}
                  </motion.span>
                )}
              </AnimatePresence>
            </motion.button>
          </div>

          {/* Back to Chat Link */}
          <div className="memory-sidebar-footer">
            <Link href="/chat" className="memory-back-link">
              <ArrowLeft size={18} />
              <AnimatePresence>
                {!sidebarCollapsed && (
                  <motion.span
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    Back to Chat
                  </motion.span>
                )}
              </AnimatePresence>
            </Link>
          </div>
        </motion.aside>

        {/* Main Content Area */}
        <main className="memory-main">
          {/* Top Header Bar */}
          <header className="memory-header">
            <div className="memory-header-left">
              <div className="memory-title-group">
                <h1 className="memory-title">
                  {viewMode === 'graph' && 'Knowledge Graph'}
                  {viewMode === 'table' && 'Memory Table'}
                  {viewMode === 'duplicates' && 'Duplicate Review'}
                </h1>
                <span className="memory-subtitle">
                  {viewMode === 'graph' && 'Explore entity relationships'}
                  {viewMode === 'table' && 'Browse and manage memories'}
                  {viewMode === 'duplicates' && 'Resolve duplicate entries'}
                </span>
              </div>
            </div>

            <div className="memory-header-right">
              {/* Search */}
              <div className="memory-search-wrapper">
                <Search size={16} className="memory-search-icon" />
                <MemorySearch
                  value={filters.searchQuery}
                  onChange={handleSearchChange}
                  placeholder={viewMode === 'graph' ? 'Search entities...' : 'Search memories...'}
                />
              </div>

              {viewMode === 'table' && (
                <div className="memory-header-sort">
                  <span className="memory-header-sort__label">Created</span>
                  <select
                    className="memory-header-sort__select"
                    value={filters.sortBy === 'created_at' ? filters.sortOrder : ''}
                    onChange={(e) => {
                      const value = e.target.value as '' | 'asc' | 'desc';
                      if (!value) return;
                      setFilters((prev) => ({
                        ...prev,
                        sortBy: 'created_at',
                        sortOrder: value,
                      }));
                    }}
                  >
                    {filters.sortBy !== 'created_at' ? (
                      <option value="">{`Current sort: ${filters.sortBy} (${filters.sortOrder})`}</option>
                    ) : null}
                    <option value="desc">Newest → Oldest</option>
                    <option value="asc">Oldest → Newest</option>
                  </select>
                </div>
              )}

              <motion.button
                className="memory-action-btn"
                onClick={handleRefresh}
                title="Refresh data"
                whileHover={{ rotate: 180 }}
                whileTap={{ scale: 0.9 }}
                transition={{ duration: 0.3 }}
              >
                <RefreshCw size={18} />
              </motion.button>
            </div>
          </header>

          {/* Content Area - Now full height without stats/filters */}
          <div className="memory-content memory-content-full">
            <AnimatePresence mode="wait">
              <motion.div
                key={viewMode}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.25 }}
                className="memory-view-container"
              >
                <Suspense
                  fallback={
                    <div className="memory-loading">
                      <motion.div
                        className="memory-loading-spinner"
                        animate={{ rotate: 360 }}
                        transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                      />
                      <p>Loading...</p>
                    </div>
                  }
                >
                  {viewMode === 'graph' && (
                    <GraphErrorBoundary
                      key={graphKey}
                      onReset={handleGraphErrorReset}
                    >
                      <MemoryGraph
                        entityFilter={effectiveEntityFilter}
                        availableEntityTypes={availableEntityTypes}
                        searchQuery={filters.searchQuery}
                        onEntityFilterChange={handleEntityTypeToggle}
                        onSelectAllEntities={handleSelectAllEntities}
                        onDeselectAllEntities={handleDeselectAllEntities}
                        onInspectMemoryFromRelationship={handleInspectMemoryFromRelationship}
                        pendingRelationshipOpen={pendingRelationshipOpen}
                        onPendingRelationshipOpenHandled={() => setPendingRelationshipOpen(null)}
                      />
                    </GraphErrorBoundary>
                  )}
                  {viewMode === 'table' && (
                    <MemoryTable
                      searchQuery={filters.searchQuery}
                      filters={filters}
                      onSortChange={(sortBy, sortOrder) => {
                        setFilters((prev) => ({ ...prev, sortBy, sortOrder }));
                      }}
                      focusMemoryId={focusedMemoryId}
                      onClearFocus={() => setFocusedMemoryId(null)}
                    />
                  )}
                  {viewMode === 'duplicates' && <DuplicateReview />}
                </Suspense>
              </motion.div>
            </AnimatePresence>
          </div>
        </main>
      </div>

      <AnimatePresence>
        {relationshipReturn && viewMode !== 'graph' ? (
          <motion.button
            key="memory-relationship-return-fab"
            className="relationship-editor-fab"
            initial={{ opacity: 0, scale: 0.92, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.92, y: 10 }}
            transition={{ type: 'spring', stiffness: 520, damping: 34 }}
            onClick={() => {
              setPendingRelationshipOpen(relationshipReturn);
              setViewMode('graph');
            }}
            type="button"
            title="Return to relationship analysis"
          >
            <Sparkles size={18} />
          </motion.button>
        ) : null}
      </AnimatePresence>

      {/* Add Memory Modal */}
      <AnimatePresence>
        {showAddForm && (
          <Suspense fallback={null}>
            <MemoryForm
              onClose={() => setShowAddForm(false)}
              onSuccess={() => {
                setShowAddForm(false);
                refetchStats();
              }}
            />
          </Suspense>
        )}
      </AnimatePresence>
    </div>
  );
}
