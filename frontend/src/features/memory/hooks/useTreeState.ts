"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TreeViewMode } from "../types";

export interface TreeCameraState {
  position: { x: number; y: number; z: number };
  target: { x: number; y: number; z: number };
}

interface PersistedTreeStateV2 {
  version: 2;
  rootNodeId: string | null;
  selectedNodeId: string | null;
  expandedNodeIds: string[];
  viewMode: TreeViewMode;
  showAllLabels: boolean;
  camera: TreeCameraState | null;
}

const STORAGE_KEY_V2 = "sparrow.memory.treeState.v2";
const STORAGE_KEY_V1 = "sparrow.memory.radialTreeState.v1";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseTreeStateV2(raw: unknown): PersistedTreeStateV2 | null {
  if (!isRecord(raw)) return null;
  if (raw.version !== 2) return null;

  const rootNodeId =
    typeof raw.rootNodeId === "string" || raw.rootNodeId === null
      ? raw.rootNodeId
      : null;

  const selectedNodeId =
    typeof raw.selectedNodeId === "string" || raw.selectedNodeId === null
      ? raw.selectedNodeId
      : null;

  const expandedNodeIds = Array.isArray(raw.expandedNodeIds)
    ? raw.expandedNodeIds.filter((id) => typeof id === "string")
    : [];

  const viewMode =
    raw.viewMode === "surface_gaps" || raw.viewMode === "celebrate_strengths"
      ? raw.viewMode
      : ("celebrate_strengths" as const);

  const showAllLabels =
    typeof raw.showAllLabels === "boolean" ? raw.showAllLabels : false;

  const cameraRaw = raw.camera;
  const camera: TreeCameraState | null =
    isRecord(cameraRaw) &&
    isRecord(cameraRaw.position) &&
    isRecord(cameraRaw.target)
      ? {
          position: {
            x:
              typeof cameraRaw.position.x === "number"
                ? cameraRaw.position.x
                : 0,
            y:
              typeof cameraRaw.position.y === "number"
                ? cameraRaw.position.y
                : 0,
            z:
              typeof cameraRaw.position.z === "number"
                ? cameraRaw.position.z
                : 0,
          },
          target: {
            x: typeof cameraRaw.target.x === "number" ? cameraRaw.target.x : 0,
            y: typeof cameraRaw.target.y === "number" ? cameraRaw.target.y : 0,
            z: typeof cameraRaw.target.z === "number" ? cameraRaw.target.z : 0,
          },
        }
      : null;

  return {
    version: 2,
    rootNodeId,
    selectedNodeId,
    expandedNodeIds,
    viewMode,
    showAllLabels,
    camera,
  };
}

function parseTreeStateV1(raw: unknown): PersistedTreeStateV2 | null {
  if (!isRecord(raw)) return null;
  if (raw.version !== 1) return null;

  const rootNodeId =
    typeof raw.rootNodeId === "string" || raw.rootNodeId === null
      ? raw.rootNodeId
      : null;

  const selectedNodeId =
    typeof raw.selectedNodeId === "string" || raw.selectedNodeId === null
      ? raw.selectedNodeId
      : null;

  const expandedNodeIds = Array.isArray(raw.expandedNodeIds)
    ? raw.expandedNodeIds.filter((id) => typeof id === "string")
    : [];

  const viewMode =
    raw.viewMode === "surface_gaps" || raw.viewMode === "celebrate_strengths"
      ? raw.viewMode
      : ("celebrate_strengths" as const);

  const showAllLabels =
    typeof raw.showAllLabels === "boolean" ? raw.showAllLabels : false;

  const cameraRaw = raw.camera;
  const camera: TreeCameraState | null =
    isRecord(cameraRaw) &&
    isRecord(cameraRaw.position) &&
    isRecord(cameraRaw.target)
      ? {
          position: {
            x:
              typeof cameraRaw.position.x === "number"
                ? cameraRaw.position.x
                : 0,
            y:
              typeof cameraRaw.position.y === "number"
                ? cameraRaw.position.y
                : 0,
            z:
              typeof cameraRaw.position.z === "number"
                ? cameraRaw.position.z
                : 0,
          },
          target: {
            x: typeof cameraRaw.target.x === "number" ? cameraRaw.target.x : 0,
            y: typeof cameraRaw.target.y === "number" ? cameraRaw.target.y : 0,
            z: typeof cameraRaw.target.z === "number" ? cameraRaw.target.z : 0,
          },
        }
      : null;

  return {
    version: 2,
    rootNodeId,
    selectedNodeId,
    expandedNodeIds,
    viewMode,
    showAllLabels,
    camera,
  };
}

function getDefaultState(): PersistedTreeStateV2 {
  return {
    version: 2,
    rootNodeId: null,
    selectedNodeId: null,
    expandedNodeIds: [],
    viewMode: "celebrate_strengths",
    showAllLabels: false,
    camera: null,
  };
}

function loadInitialState(): PersistedTreeStateV2 {
  if (typeof window === "undefined") {
    return getDefaultState();
  }

  try {
    const rawV2 = window.localStorage.getItem(STORAGE_KEY_V2);
    if (rawV2) {
      const parsed = parseTreeStateV2(JSON.parse(rawV2));
      if (parsed) return parsed;
    }

    const rawV1 = window.localStorage.getItem(STORAGE_KEY_V1);
    if (rawV1) {
      const parsed = parseTreeStateV1(JSON.parse(rawV1));
      if (parsed) return parsed;
    }

    return getDefaultState();
  } catch {
    return getDefaultState();
  }
}

export function useTreeState() {
  const initial = useMemo(() => loadInitialState(), []);

  const [rootNodeId, setRootNodeId] = useState<string | null>(
    initial.rootNodeId,
  );
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    initial.selectedNodeId ?? null,
  );
  const [expandedNodeIds, setExpandedNodeIds] = useState<string[]>(
    initial.expandedNodeIds,
  );
  const [viewMode, setViewMode] = useState<TreeViewMode>(initial.viewMode);
  const [showAllLabels, setShowAllLabels] = useState<boolean>(
    initial.showAllLabels ?? false,
  );

  const cameraRef = useRef<TreeCameraState | null>(initial.camera ?? null);

  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const persist = useCallback(() => {
    if (typeof window === "undefined") return;

    if (persistTimerRef.current) {
      clearTimeout(persistTimerRef.current);
    }

    persistTimerRef.current = setTimeout(() => {
      try {
        const payload: PersistedTreeStateV2 = {
          version: 2,
          rootNodeId,
          selectedNodeId,
          expandedNodeIds,
          viewMode,
          showAllLabels,
          camera: cameraRef.current,
        };
        window.localStorage.setItem(STORAGE_KEY_V2, JSON.stringify(payload));
      } catch {
        // Ignore storage failures (private mode / quota).
      }
    }, 250);
  }, [expandedNodeIds, rootNodeId, selectedNodeId, showAllLabels, viewMode]);

  useEffect(() => {
    persist();
    return () => {
      if (persistTimerRef.current) {
        clearTimeout(persistTimerRef.current);
      }
    };
  }, [persist]);

  const expandedNodeIdSet = useMemo(
    () => new Set(expandedNodeIds),
    [expandedNodeIds],
  );

  const toggleExpandedNode = useCallback((nodeId: string) => {
    setExpandedNodeIds((prev) => {
      const set = new Set(prev);
      if (set.has(nodeId)) set.delete(nodeId);
      else set.add(nodeId);
      return Array.from(set.values());
    });
  }, []);

  const setCamera = useCallback((next: TreeCameraState | null) => {
    cameraRef.current = next;
  }, []);

  const reset = useCallback(() => {
    setRootNodeId(null);
    setSelectedNodeId(null);
    setExpandedNodeIds([]);
    setViewMode("celebrate_strengths");
    setShowAllLabels(false);
    cameraRef.current = null;

    if (typeof window !== "undefined") {
      try {
        window.localStorage.removeItem(STORAGE_KEY_V2);
        window.localStorage.removeItem(STORAGE_KEY_V1);
      } catch {
        // ignore
      }
    }
  }, []);

  return {
    rootNodeId,
    setRootNodeId,
    selectedNodeId,
    setSelectedNodeId,
    expandedNodeIds,
    expandedNodeIdSet,
    setExpandedNodeIds,
    toggleExpandedNode,
    viewMode,
    setViewMode,
    showAllLabels,
    setShowAllLabels,
    initialCamera: initial.camera ?? null,
    setCamera,
    persist,
    reset,
  };
}
