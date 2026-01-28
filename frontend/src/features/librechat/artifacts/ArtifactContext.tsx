'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { create } from 'zustand';
import type { Artifact, ArtifactStore } from './types';

/**
 * Zustand store for artifact state management
 * 
 * Manages artifacts extracted from chat messages, including:
 * - Storage of all artifacts by ID
 * - Current artifact selection
 * - Panel visibility state
 * - Ordered list for navigation
 */
const createArtifactStore = () =>
  create<ArtifactStore>((set, get) => ({
    // State
    artifactsById: {},
    currentArtifactId: null,
    isArtifactsVisible: false,
    orderedIds: [],

    // Actions
    addArtifact: (artifact: Artifact) => {
      set((state) => {
        const exists = state.artifactsById[artifact.id];
        
        // Update ordered IDs if this is a new artifact
        const orderedIds = exists
          ? state.orderedIds
          : [...state.orderedIds, artifact.id];

        return {
          artifactsById: {
            ...state.artifactsById,
            [artifact.id]: {
              ...artifact,
              lastUpdateTime: Date.now(),
            },
          },
          orderedIds,
        };
      });
    },

    setCurrentArtifact: (id: string | null) => {
      set({ currentArtifactId: id });
    },

    setArtifactsVisible: (visible: boolean) => {
      set({ isArtifactsVisible: visible });
    },

    resetArtifacts: () => {
      set({
        artifactsById: {},
        currentArtifactId: null,
        isArtifactsVisible: false,
        orderedIds: [],
      });
    },

    removeArtifact: (id: string) => {
      set((state) => {
        const { [id]: removed, ...remaining } = state.artifactsById;
        const orderedIds = state.orderedIds.filter((aid) => aid !== id);
        
        // If removing the current artifact, clear selection
        const currentArtifactId =
          state.currentArtifactId === id ? null : state.currentArtifactId;

        return {
          artifactsById: remaining,
          orderedIds,
          currentArtifactId,
        };
      });
    },

    getArtifact: (id: string) => {
      return get().artifactsById[id];
    },

    getArtifactsByMessage: (messageId: string) => {
      const { artifactsById, orderedIds } = get();
      return orderedIds
        .map((id) => artifactsById[id])
        .filter((a): a is Artifact => a?.messageId === messageId);
    },
  }));

// Type for the store
type ArtifactStoreType = ReturnType<typeof createArtifactStore>;

// Global store reference for imperative access (e.g., from event handlers)
let globalArtifactStore: ArtifactStoreType | null = null;

/**
 * Get the global artifact store for imperative access.
 * Returns null if no ArtifactProvider is mounted.
 */
export function getGlobalArtifactStore(): ArtifactStoreType | null {
  return globalArtifactStore;
}

// Context to provide store instance
const ArtifactStoreContext = createContext<ArtifactStoreType | null>(null);

/**
 * Provider component for artifact store
 * Wraps the application to provide artifact state management
 */
export function ArtifactProvider({ children }: { children: React.ReactNode }) {
  const [store] = useState(() => {
    const newStore = createArtifactStore();
    globalArtifactStore = newStore;
    return newStore;
  });

  useEffect(() => {
    return () => {
      if (globalArtifactStore === store) {
        globalArtifactStore = null;
      }
    };
  }, [store]);

  return (
    <ArtifactStoreContext.Provider value={store}>
      {children}
    </ArtifactStoreContext.Provider>
  );
}

/**
 * Hook to access the artifact store
 * Must be used within ArtifactProvider
 */
export function useArtifactStore(): ArtifactStore {
  const store = useContext(ArtifactStoreContext);
  if (!store) {
    throw new Error('useArtifactStore must be used within ArtifactProvider');
  }
  return store();
}

/**
 * Hook to access specific artifact store selectors
 * Provides memoized access to prevent unnecessary re-renders
 */
export function useArtifactSelector<T>(selector: (state: ArtifactStore) => T): T {
  const store = useContext(ArtifactStoreContext);
  if (!store) {
    throw new Error('useArtifactSelector must be used within ArtifactProvider');
  }
  return store(selector);
}

/**
 * Hook for current artifact
 */
export function useCurrentArtifact(): Artifact | null {
  const currentId = useArtifactSelector((s) => s.currentArtifactId);
  const artifactsById = useArtifactSelector((s) => s.artifactsById);
  return currentId ? artifactsById[currentId] ?? null : null;
}

/**
 * Hook for artifact visibility
 */
export function useArtifactsVisible(): boolean {
  return useArtifactSelector((s) => s.isArtifactsVisible);
}

/**
 * Hook for artifact actions
 */
export function useArtifactActions() {
  const store = useContext(ArtifactStoreContext);
  if (!store) {
    throw new Error('useArtifactActions must be used within ArtifactProvider');
  }

  const state = store.getState();

  return {
    addArtifact: state.addArtifact,
    setCurrentArtifact: state.setCurrentArtifact,
    setArtifactsVisible: state.setArtifactsVisible,
    resetArtifacts: state.resetArtifacts,
    removeArtifact: state.removeArtifact,
  };
}

// Re-export types for convenience
export type { Artifact, ArtifactStore } from './types';
