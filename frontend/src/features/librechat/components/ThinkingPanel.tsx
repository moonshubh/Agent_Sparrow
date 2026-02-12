"use client";

import React, {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Compass,
  Database,
  Eye,
  EyeOff,
  ListChecks,
  Loader2,
  Search,
  Sparkles,
  Wrench,
  Zap,
} from "lucide-react";
import { EnhancedMarkdown } from "./EnhancedMarkdown";
import type { TodoItem, ToolEvidenceCard } from "@/services/ag-ui/event-types";
import type {
  PanelLane,
  PanelObjective,
  PanelObjectiveStatus,
  PanelState,
} from "@/features/librechat/panel-event-adapter";
import { PANEL_PRIMARY_PHASE_ORDER } from "@/features/librechat/panel-event-adapter";
import type { WebSearchMode } from "@/features/librechat/AgentContext";

type ResearchStatus = "idle" | "running" | "stuck" | "failed";
type PanelFilter = "all" | "active" | "thought" | "tool" | "todo" | "error";

interface ThinkingPanelProps {
  panelState: PanelState;
  isStreaming?: boolean;
  sessionId?: string;
  activeTools?: string[];
  todos?: TodoItem[];
  researchProgress?: number;
  researchStatus?: ResearchStatus;
  webSearchMode?: WebSearchMode;
  enableKeyboardShortcuts?: boolean;
}

interface ThinkingStickyRailProps {
  panelState: PanelState;
  isStreaming?: boolean;
  todos?: TodoItem[];
  activeTools?: string[];
  webSearchMode?: WebSearchMode;
}

const PANEL_FILTERS: ReadonlyArray<{
  id: PanelFilter;
  label: string;
}> = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "thought", label: "Thought" },
  { id: "tool", label: "Tool" },
  { id: "todo", label: "Todo" },
  { id: "error", label: "Error" },
];

const clampText = (value: string, max: number): string =>
  value.length > max ? `${value.slice(0, max).trimEnd()}...` : value;

const statusLabel = (status: PanelObjectiveStatus): string => {
  switch (status) {
    case "pending":
      return "Pending";
    case "running":
      return "Running";
    case "done":
      return "Done";
    case "error":
      return "Error";
    case "unknown":
      return "Unknown";
    default:
      return "Pending";
  }
};

const statusIcon = (status: PanelObjectiveStatus): React.ReactNode => {
  if (status === "error") return <AlertCircle size={12} />;
  if (status === "running") return <Loader2 size={12} className="lc-spin" />;
  if (status === "done") return <Sparkles size={12} />;
  if (status === "unknown") return <Compass size={12} />;
  return <Zap size={12} />;
};

const objectiveIcon = (objective: PanelObjective): React.ReactNode => {
  if (objective.status === "error") {
    return <AlertCircle size={14} className="lc-think-objective-icon-error" />;
  }
  if (objective.kind === "todo") {
    return <ListChecks size={14} />;
  }
  if (objective.kind === "tool") {
    const label = `${objective.title} ${objective.summary ?? ""}`.toLowerCase();
    if (label.includes("search") || label.includes("web")) return <Search size={14} />;
    if (label.includes("db") || label.includes("database")) {
      return <Database size={14} />;
    }
    return <Wrench size={14} />;
  }
  return <Sparkles size={14} />;
};

const phaseLabel = (phase: string): string => {
  if (!phase) return "Execute";
  return phase.charAt(0).toUpperCase() + phase.slice(1);
};

const matchesFilter = (objective: PanelObjective, filter: PanelFilter): boolean => {
  switch (filter) {
    case "all":
      return true;
    case "active":
      return objective.status === "pending" || objective.status === "running";
    case "thought":
      return objective.kind === "thought";
    case "tool":
      return objective.kind === "tool";
    case "todo":
      return objective.kind === "todo";
    case "error":
      return objective.kind === "error" || objective.status === "error";
    default:
      return true;
  }
};

const sortObjectiveIds = (
  objectiveIds: string[],
  objectives: Record<string, PanelObjective>,
): string[] => {
  return [...objectiveIds].sort((a, b) => {
    const left = objectives[a];
    const right = objectives[b];
    const leftTs = Date.parse(left?.updatedAt ?? left?.startedAt ?? "") || 0;
    const rightTs = Date.parse(right?.updatedAt ?? right?.startedAt ?? "") || 0;
    return leftTs - rightTs;
  });
};

const summarizeTodos = (todos: TodoItem[]): { done: number; total: number } => {
  const total = todos.length;
  const done = todos.filter((todo) => todo.status === "done").length;
  return { done, total };
};

const formatRelativeDuration = (start?: string, end?: string): string | null => {
  if (!start) return null;
  const startMs = Date.parse(start);
  if (!Number.isFinite(startMs)) return null;
  const endMs = end ? Date.parse(end) : Date.now();
  if (!Number.isFinite(endMs)) return null;
  const seconds = Math.max(0, Math.round((endMs - startMs) / 1000));
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const rem = seconds % 60;
  return rem ? `${mins}m ${rem}s` : `${mins}m`;
};

const ensureSummary = (objective: PanelObjective): string => {
  if (objective.summary?.trim()) return objective.summary.trim();
  if (objective.detail?.trim()) return clampText(objective.detail.trim(), 180);
  return objective.status === "running" ? "In progress" : "No summary yet";
};

const shouldRenderMarkdown = (objective: PanelObjective): boolean => {
  if (objective.kind !== "thought") return false;
  const detail = objective.detail ?? objective.summary;
  if (!detail) return false;
  const sample = detail.trim();
  if (!sample) return false;
  return /[#*_`\-\[\]\(\)]/.test(sample);
};

const hostForCard = (card: ToolEvidenceCard): string | null => {
  if (typeof card.url === "string" && card.url.trim()) {
    try {
      return new URL(card.url).host;
    } catch {
      return null;
    }
  }
  if (typeof card.metadata?.host === "string" && card.metadata.host.trim()) {
    return card.metadata.host;
  }
  return null;
};

const groupObjectivesByPhase = (
  lane: PanelLane,
  objectives: Record<string, PanelObjective>,
): Array<{ phase: string; objectiveIds: string[] }> => {
  const sortedIds = sortObjectiveIds(lane.objectiveIds, objectives);
  if (lane.id !== "primary") {
    return [{ phase: "execute", objectiveIds: sortedIds }];
  }

  const byPhase = new Map<string, string[]>();
  sortedIds.forEach((objectiveId) => {
    const objective = objectives[objectiveId];
    if (!objective) return;
    const phase = objective.phase || "execute";
    if (!byPhase.has(phase)) {
      byPhase.set(phase, []);
    }
    byPhase.get(phase)?.push(objectiveId);
  });

  const sections: Array<{ phase: string; objectiveIds: string[] }> = [];
  PANEL_PRIMARY_PHASE_ORDER.forEach((phase) => {
    const ids = byPhase.get(phase) ?? [];
    sections.push({ phase, objectiveIds: ids });
  });

  byPhase.forEach((ids, phase) => {
    if (!PANEL_PRIMARY_PHASE_ORDER.includes(phase as (typeof PANEL_PRIMARY_PHASE_ORDER)[number])) {
      sections.push({ phase, objectiveIds: ids });
    }
  });

  return sections;
};

const readPersistedFilter = (storageKey: string): PanelFilter => {
  if (typeof window === "undefined") return "all";
  const stored = window.localStorage.getItem(storageKey);
  if (!stored) return "all";
  const normalized = stored.toLowerCase();
  return PANEL_FILTERS.some((item) => item.id === normalized)
    ? (normalized as PanelFilter)
    : "all";
};

const isEditableTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select";
};

export const ThinkingStickyRail = memo(function ThinkingStickyRail({
  panelState,
  isStreaming = false,
  todos = [],
  activeTools = [],
  webSearchMode = "off",
}: ThinkingStickyRailProps) {
  const { done, total } = useMemo(() => summarizeTodos(todos), [todos]);
  const runningTools = activeTools.length;
  const runLabel = isStreaming
    ? "Running"
    : panelState.runStatus === "error"
      ? "Issue detected"
      : panelState.runStatus === "done"
        ? "Completed"
        : panelState.runStatus === "unknown"
          ? "Limited"
          : panelState.runStatus === "running"
            ? "Running"
            : "Ready";

  return (
    <div className="lc-thinking-rail">
      <div className="lc-thinking-rail-main">
        <span className={`lc-thinking-rail-dot ${isStreaming ? "active" : ""}`} />
        <span className="lc-thinking-rail-status">{runLabel}</span>
        <span className="lc-thinking-rail-divider" aria-hidden="true">
          •
        </span>
        <span className="lc-thinking-rail-meta">
          {total > 0 ? `${done}/${total} todos` : "No todos"}
        </span>
        {runningTools > 0 && (
          <>
            <span className="lc-thinking-rail-divider" aria-hidden="true">
              •
            </span>
            <span className="lc-thinking-rail-meta">{runningTools} tool{runningTools === 1 ? "" : "s"}</span>
          </>
        )}
      </div>
      <span className={`lc-web-mode-badge ${webSearchMode === "on" ? "on" : "off"}`}>
        Web {webSearchMode === "on" ? "On" : "Off"}
      </span>
    </div>
  );
});

export const ThinkingPanel = memo(function ThinkingPanel({
  panelState,
  isStreaming = false,
  sessionId,
  activeTools = [],
  todos = [],
  researchProgress = 0,
  researchStatus = "idle",
  webSearchMode = "off",
  enableKeyboardShortcuts = false,
}: ThinkingPanelProps) {
  const [isExpanded, setIsExpanded] = useState<boolean>(() => isStreaming);
  const [expandedLaneIds, setExpandedLaneIds] = useState<Set<string>>(
    () => new Set([panelState.activeLaneId]),
  );
  const [expandedObjectiveIds, setExpandedObjectiveIds] = useState<Set<string>>(
    new Set(),
  );
  const [expandedEvidenceObjectiveIds, setExpandedEvidenceObjectiveIds] = useState<Set<string>>(
    new Set(),
  );
  const [activeFilter, setActiveFilter] = useState<PanelFilter>(() =>
    readPersistedFilter(`lc-thinking-filter:${sessionId ?? "global"}`),
  );
  const [autoFollow, setAutoFollow] = useState(true);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const contentRef = useRef<HTMLDivElement | null>(null);

  const filterStorageKey = useMemo(
    () => `lc-thinking-filter:${sessionId ?? "global"}`,
    [sessionId],
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(filterStorageKey, activeFilter);
  }, [activeFilter, filterStorageKey]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => {
      setPrefersReducedMotion(query.matches);
    };
    apply();
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", apply);
      return () => query.removeEventListener("change", apply);
    }
    query.addListener(apply);
    return () => query.removeListener(apply);
  }, []);

  const panelExpanded = isExpanded || isStreaming;

  const expandedLaneIdsForRender = useMemo(() => {
    if (!isStreaming) return expandedLaneIds;
    const next = new Set(expandedLaneIds);
    next.add(panelState.activeLaneId || "primary");
    return next;
  }, [expandedLaneIds, isStreaming, panelState.activeLaneId]);

  const expandedObjectiveIdsForRender = useMemo(() => {
    const next = new Set(expandedObjectiveIds);
    Object.values(panelState.objectives)
      .filter((objective) => objective.status === "error")
      .forEach((objective) => next.add(objective.id));
    return next;
  }, [expandedObjectiveIds, panelState.objectives]);

  const laneViewModels = useMemo(() => {
    return panelState.laneOrder
      .map((laneId) => panelState.lanes[laneId])
      .filter((lane): lane is PanelLane => Boolean(lane))
      .map((lane) => {
        const groupedSections = groupObjectivesByPhase(lane, panelState.objectives)
          .map((section) => ({
            phase: section.phase,
            objectiveIds: section.objectiveIds.filter((objectiveId) => {
              const objective = panelState.objectives[objectiveId];
              return objective ? matchesFilter(objective, activeFilter) : false;
            }),
          }))
          .filter((section) => section.objectiveIds.length > 0);

        return {
          lane,
          groupedSections,
          visibleObjectiveCount: groupedSections.reduce(
            (sum, section) => sum + section.objectiveIds.length,
            0,
          ),
        };
      })
      .filter((entry) => entry.visibleObjectiveCount > 0);
  }, [activeFilter, panelState.laneOrder, panelState.lanes, panelState.objectives]);

  const hasContent = laneViewModels.length > 0 || todos.length > 0 || activeTools.length > 0;

  const latestVisibleObjectiveId = useMemo(() => {
    const visibleObjectives = laneViewModels.flatMap((laneEntry) =>
      laneEntry.groupedSections.flatMap((section) => section.objectiveIds),
    );
    if (!visibleObjectives.length) return undefined;
    return visibleObjectives[visibleObjectives.length - 1];
  }, [laneViewModels]);

  useEffect(() => {
    if (!panelExpanded || !autoFollow) return;
    const targetId = panelState.activeObjectiveId ?? latestVisibleObjectiveId;
    if (!targetId) return;

    const container = contentRef.current;
    if (!container) return;

    const safeTargetId =
      typeof CSS !== "undefined" && typeof CSS.escape === "function"
        ? CSS.escape(targetId)
        : targetId;
    const target = container.querySelector(
      `[data-objective-id="${safeTargetId}"]`,
    ) as HTMLElement | null;
    if (!target) return;

    requestAnimationFrame(() => {
      target.scrollIntoView({
        block: "nearest",
        behavior: prefersReducedMotion ? "auto" : "smooth",
      });
    });
  }, [
    autoFollow,
    panelExpanded,
    latestVisibleObjectiveId,
    panelState.activeObjectiveId,
    panelState.updatedAt,
    prefersReducedMotion,
  ]);

  const onContentScroll = useCallback(() => {
    const container = contentRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceFromBottom > 36) {
      setAutoFollow(false);
    } else if (isStreaming) {
      setAutoFollow(true);
    }
  }, [isStreaming]);

  const toggleLane = useCallback((laneId: string) => {
    setExpandedLaneIds((prev) => {
      const next = new Set(prev);
      if (next.has(laneId)) {
        next.delete(laneId);
      } else {
        next.add(laneId);
      }
      return next;
    });
  }, []);

  const toggleObjective = useCallback((objectiveId: string) => {
    setExpandedObjectiveIds((prev) => {
      const next = new Set(prev);
      if (next.has(objectiveId)) {
        next.delete(objectiveId);
      } else {
        next.add(objectiveId);
      }
      return next;
    });
  }, []);

  const toggleEvidenceExpansion = useCallback((objectiveId: string) => {
    setExpandedEvidenceObjectiveIds((prev) => {
      const next = new Set(prev);
      if (next.has(objectiveId)) {
        next.delete(objectiveId);
      } else {
        next.add(objectiveId);
      }
      return next;
    });
  }, []);

  const togglePanelExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  const cycleFilter = useCallback(() => {
    setActiveFilter((prev) => {
      const currentIndex = PANEL_FILTERS.findIndex((filter) => filter.id === prev);
      const safeIndex = currentIndex < 0 ? 0 : currentIndex;
      return PANEL_FILTERS[(safeIndex + 1) % PANEL_FILTERS.length].id;
    });
  }, []);

  useEffect(() => {
    if (!enableKeyboardShortcuts) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat) return;
      if (!(event.metaKey || event.ctrlKey) || !event.shiftKey || event.altKey) {
        return;
      }
      if (isEditableTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === "p") {
        event.preventDefault();
        togglePanelExpanded();
        return;
      }
      if (key === "f") {
        event.preventDefault();
        setIsExpanded(true);
        cycleFilter();
        return;
      }
      if (key === "a") {
        event.preventDefault();
        setAutoFollow((prev) => !prev);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [cycleFilter, enableKeyboardShortcuts, togglePanelExpanded]);

  const shortcutModifierLabel = useMemo(() => {
    if (typeof navigator !== "undefined" && /mac/i.test(navigator.platform)) {
      return "Cmd+Shift";
    }
    return "Ctrl+Shift";
  }, []);

  const { done: todosDone, total: todosTotal } = useMemo(() => summarizeTodos(todos), [todos]);

  if (!hasContent) return null;

  return (
    <section className="lc-think" aria-label="Reasoning panel">
      <header className="lc-think-header">
        <button
          type="button"
          className="lc-think-header-button"
          onClick={togglePanelExpanded}
          aria-expanded={panelExpanded}
          aria-keyshortcuts={
            enableKeyboardShortcuts
              ? "Meta+Shift+P Control+Shift+P"
              : undefined
          }
        >
          <span className="lc-think-header-left">
            {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            <span className="lc-think-header-title">Reasoning Timeline</span>
            <span className="lc-think-header-meta">
              {Object.keys(panelState.objectives).length} objectives
            </span>
          </span>
          <span className={`lc-web-mode-badge ${webSearchMode === "on" ? "on" : "off"}`}>
            Web {webSearchMode === "on" ? "On" : "Off"}
          </span>
        </button>
      </header>

      {panelExpanded && (
        <>
          <div className="lc-think-topline">
            {panelState.runStatus === "unknown" && (
              <div className="lc-think-limited-pill" role="status" aria-live="polite">
                Reasoning ended with incomplete signals.
              </div>
            )}
            {researchStatus !== "idle" && (
              <div className={`lc-think-research-pill ${researchStatus}`}>
                <span className="lc-think-research-dot" />
                <span>
                  {researchStatus === "running"
                    ? `Research ${Math.min(100, Math.max(0, Math.round(researchProgress)))}%`
                    : researchStatus === "stuck"
                      ? "Research delayed"
                      : "Research failed"}
                </span>
              </div>
            )}
            {activeTools.length > 0 && (
              <div className="lc-think-tool-strip" aria-label="Active tools">
                {activeTools.map((tool, index) => (
                  <span key={`${tool}-${index}`} className="lc-think-tool-pill">
                    <Loader2 size={11} className="lc-spin" />
                    {tool.replace(/[_-]+/g, " ")}
                  </span>
                ))}
              </div>
            )}
            {todosTotal > 0 && (
              <div className="lc-think-todo-pill">Todos {todosDone}/{todosTotal}</div>
            )}
          </div>

          <div className="lc-think-filters" role="group" aria-label="Reasoning filters">
            {PANEL_FILTERS.map((filter) => (
              <button
                key={filter.id}
                type="button"
                aria-pressed={activeFilter === filter.id}
                className={`lc-think-filter-chip ${activeFilter === filter.id ? "active" : ""}`}
                onClick={() => setActiveFilter(filter.id)}
                aria-keyshortcuts={
                  enableKeyboardShortcuts && filter.id === activeFilter
                    ? "Meta+Shift+F Control+Shift+F"
                    : undefined
                }
              >
                {filter.label}
              </button>
            ))}
            {!autoFollow && (
              <button
                type="button"
                className="lc-think-follow-btn"
                onClick={() => setAutoFollow(true)}
                aria-keyshortcuts={
                  enableKeyboardShortcuts
                    ? "Meta+Shift+A Control+Shift+A"
                    : undefined
                }
              >
                <Eye size={12} />
                Follow latest
              </button>
            )}
            {autoFollow && (
              <span className="lc-think-follow-hint">
                <EyeOff size={12} />
                Auto-follow on
              </span>
            )}
            {enableKeyboardShortcuts && (
              <span className="lc-think-shortcut-hint">
                Shortcuts: {shortcutModifierLabel}+P panel, {shortcutModifierLabel}+F
                filter, {shortcutModifierLabel}+A follow
              </span>
            )}
          </div>

          <div
            className="lc-think-body"
            ref={contentRef}
            onScroll={onContentScroll}
            role="region"
            aria-label="Reasoning details"
          >
            {laneViewModels.map((laneEntry) => {
              const { lane, groupedSections } = laneEntry;
              const isLaneExpanded = expandedLaneIdsForRender.has(lane.id);
              const laneObjectiveCount = groupedSections.reduce(
                (sum, section) => sum + section.objectiveIds.length,
                0,
              );

              return (
                <section key={lane.id} className="lc-think-lane">
                  <button
                    type="button"
                    className="lc-think-lane-header"
                    onClick={() => toggleLane(lane.id)}
                    aria-expanded={isLaneExpanded}
                  >
                    <span className="lc-think-lane-left">
                      {isLaneExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      <span className="lc-think-lane-title">{lane.title}</span>
                    </span>
                    <span className="lc-think-lane-right">
                      <span className={`lc-think-status-pill ${lane.status}`}>
                        {statusIcon(lane.status)}
                        {statusLabel(lane.status)}
                      </span>
                      <span className="lc-think-lane-count">{laneObjectiveCount}</span>
                    </span>
                  </button>

                  {isLaneExpanded && (
                    <div className="lc-think-lane-content">
                      {groupedSections.map((section) => (
                        <div key={`${lane.id}-${section.phase}`} className="lc-think-phase-block">
                          <div className="lc-think-phase-label">{phaseLabel(section.phase)}</div>

                          <div className="lc-think-objective-list">
                            {section.objectiveIds.map((objectiveId) => {
                              const objective = panelState.objectives[objectiveId];
                              if (!objective) return null;

                              const isObjectiveExpanded = expandedObjectiveIdsForRender.has(
                                objective.id,
                              );
                              const summary = ensureSummary(objective);
                              const cards = objective.evidenceCards ?? [];
                              const cardsExpanded = expandedEvidenceObjectiveIds.has(objective.id);
                              const visibleCards = cardsExpanded ? cards : cards.slice(0, 3);
                              const duration = formatRelativeDuration(
                                objective.startedAt,
                                objective.endedAt,
                              );

                              return (
                                <article
                                  key={objective.id}
                                  className={`lc-think-objective ${objective.status === "error" ? "error" : ""}`}
                                  data-objective-id={objective.id}
                                >
                                  <button
                                    type="button"
                                    className="lc-think-objective-head"
                                    onClick={() => toggleObjective(objective.id)}
                                    aria-expanded={isObjectiveExpanded}
                                  >
                                    <span className="lc-think-objective-head-left">
                                      {isObjectiveExpanded ? (
                                        <ChevronDown size={13} />
                                      ) : (
                                        <ChevronRight size={13} />
                                      )}
                                      <span className="lc-think-objective-icon">
                                        {objectiveIcon(objective)}
                                      </span>
                                      <span className="lc-think-objective-title">{objective.title}</span>
                                    </span>
                                    <span className="lc-think-objective-head-right">
                                      {duration && (
                                        <span className="lc-think-duration">{duration}</span>
                                      )}
                                      <span className={`lc-think-status-pill ${objective.status}`}>
                                        {statusIcon(objective.status)}
                                        {statusLabel(objective.status)}
                                      </span>
                                    </span>
                                  </button>

                                  <div className="lc-think-objective-summary">{clampText(summary, 220)}</div>

                                  {isObjectiveExpanded && (
                                    <div className="lc-think-objective-detail">
                                      {objective.detail && shouldRenderMarkdown(objective) ? (
                                        <EnhancedMarkdown
                                          content={objective.detail}
                                          variant="librechat"
                                          messageId={objective.id}
                                          registerArtifacts={false}
                                        />
                                      ) : objective.detail ? (
                                        <p>{objective.detail}</p>
                                      ) : null}

                                      {visibleCards.length > 0 && (
                                        <div className="lc-think-evidence-list">
                                          {visibleCards.map((card, idx) => {
                                            const Wrapper: React.ElementType = card.url ? "a" : "div";
                                            const host = hostForCard(card);
                                            const title = card.title || `Evidence ${idx + 1}`;
                                            const snippet = card.snippet || "";
                                            return (
                                              <Wrapper
                                                key={`${objective.id}-card-${idx}`}
                                                className="lc-think-evidence-card"
                                                {...(card.url
                                                  ? {
                                                      href: card.url,
                                                      target: "_blank",
                                                      rel: "noreferrer",
                                                    }
                                                  : {})}
                                              >
                                                <div className="lc-think-evidence-title">{title}</div>
                                                {snippet && (
                                                  <div className="lc-think-evidence-snippet">{snippet}</div>
                                                )}
                                                {(host || card.type) && (
                                                  <div className="lc-think-evidence-meta">
                                                    {host || card.type}
                                                  </div>
                                                )}
                                              </Wrapper>
                                            );
                                          })}
                                        </div>
                                      )}

                                      {cards.length > 3 && (
                                        <button
                                          type="button"
                                          className="lc-think-more-cards"
                                          onClick={() => toggleEvidenceExpansion(objective.id)}
                                        >
                                          {cardsExpanded
                                            ? "Show fewer evidence cards"
                                            : `Show all ${cards.length} evidence cards`}
                                        </button>
                                      )}
                                    </div>
                                  )}
                                </article>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
});

export default ThinkingPanel;
