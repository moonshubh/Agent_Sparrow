/**
 * UI Store - Interface State Management
 *
 * Handles UI-specific state including navigation, modals, view modes,
 * and user interface preferences.
 */

import { create } from "zustand";
import { devtools, subscribeWithSelector, persist } from "zustand/middleware";

// Sidebar width constraints
const MIN_SIDEBAR_WIDTH = 200;
const MAX_SIDEBAR_WIDTH = 500;

// Types
export interface TabState {
  activeTab: "conversations" | "folders" | "analytics" | "upload" | "search";
  tabHistory: string[];
  canGoBack: boolean;
  canGoForward: boolean;
}

export interface ViewState {
  viewMode: "grid" | "list" | "table" | "cards";
  itemsPerPage: number;
  sortColumn: string | null;
  sortDirection: "asc" | "desc";
  compactMode: boolean;
  showPreview: boolean;
}

export interface ModalState {
  activeModal: string | null;
  modalData: Record<string, unknown>;
  modalHistory: string[];
}

export interface SidebarState {
  isCollapsed: boolean;
  width: number;
  pinnedSections: Set<string>;
  expandedSections: Set<string>;
  showFolderPanel: boolean;
  activeFolderId: number | null;
}

export interface BulkActionState {
  isEnabled: boolean;
  selectedItems: Set<string | number>;
  availableActions: string[];
  activeAction: string | null;
}

export interface NotificationState {
  toasts: Array<{
    id: string;
    type: "info" | "success" | "warning" | "error";
    title: string;
    message: string;
    duration?: number;
    actions?: Array<{ label: string; action: () => void }>;
  }>;
  banners: Array<{
    id: string;
    type: "info" | "success" | "warning" | "error";
    message: string;
    dismissible: boolean;
    persistent: boolean;
  }>;
}

export interface LoadingState {
  global: boolean;
  sections: Record<string, boolean>;
  operations: Record<string, boolean>;
}

export interface ThemeState {
  theme: "light" | "dark" | "system";
  accentColor: string;
  fontSize: "small" | "medium" | "large";
  animations: boolean;
  reducedMotion: boolean;
}

export interface PanelState {
  leftWidth: number;
  leftPanel: "folders" | "search";
  rightPanel: "conversations" | "analytics" | "editor";
  selectedConversationId: number | null;
}

interface UIState {
  // Navigation & Tabs (legacy - maintain compatibility)
  tabs: TabState;

  // New Panel System
  panels: PanelState;

  // View Configuration
  view: ViewState;

  // Modal Management
  modals: ModalState;

  // Layout
  sidebar: SidebarState;

  // Bulk Operations
  bulkActions: BulkActionState;

  // Notifications
  notifications: NotificationState;

  // Loading States
  loading: LoadingState;

  // Theme & Preferences
  theme: ThemeState;

  // Keyboard Navigation
  keyboardNavigation: {
    enabled: boolean;
    currentFocus: string | null;
    focusHistory: string[];
  };
}

interface UIActions {
  // Tab Management (legacy - maintain compatibility)
  setActiveTab: (tab: TabState["activeTab"]) => void;
  navigateBack: () => void;
  navigateForward: () => void;

  // Panel Management
  setPanelWidth: (width: number) => void;
  setLeftPanel: (panel: PanelState["leftPanel"]) => void;
  setRightPanel: (panel: PanelState["rightPanel"]) => void;
  selectConversation: (id: number | null) => void;

  // View Management
  setViewMode: (mode: ViewState["viewMode"]) => void;
  setItemsPerPage: (count: number) => void;
  setSorting: (
    column: string | null,
    direction: ViewState["sortDirection"],
  ) => void;
  toggleCompactMode: () => void;
  togglePreview: () => void;

  // Modal Management
  openModal: (modalId: string, data?: Record<string, unknown>) => void;
  closeModal: () => void;
  closeAllModals: () => void;

  // Sidebar Management
  toggleSidebar: () => void;
  setSidebarWidth: (width: number) => void;
  toggleSidebarSection: (sectionId: string) => void;
  pinSidebarSection: (sectionId: string, pinned: boolean) => void;
  openFolderPanel: () => void;
  closeFolderPanel: () => void;
  toggleFolderPanel: () => void;
  setActiveFolder: (folderId: number | null) => void;
  openFolderPanelHover: () => void;
  closeFolderPanelHover: () => void;
  clearHoverTimers: () => void;

  // Bulk Actions
  enableBulkActions: (actions: string[]) => void;
  disableBulkActions: () => void;
  selectBulkItem: (itemId: string | number, selected: boolean) => void;
  selectAllBulkItems: (items: (string | number)[], selected: boolean) => void;
  clearBulkSelection: () => void;
  setBulkAction: (action: string | null) => void;

  // Notification Management
  showToast: (
    toast: Omit<UIState["notifications"]["toasts"][0], "id">,
  ) => string;
  hideToast: (id: string) => void;
  clearToasts: () => void;
  showBanner: (
    banner: Omit<UIState["notifications"]["banners"][0], "id">,
  ) => string;
  hideBanner: (id: string) => void;
  clearBanners: () => void;

  // Loading States
  setGlobalLoading: (loading: boolean) => void;
  setSectionLoading: (section: string, loading: boolean) => void;
  setOperationLoading: (operation: string, loading: boolean) => void;
  clearAllLoading: () => void;

  // Theme Management
  setTheme: (theme: ThemeState["theme"]) => void;
  setAccentColor: (color: string) => void;
  setFontSize: (size: ThemeState["fontSize"]) => void;
  toggleAnimations: () => void;
  setReducedMotion: (reduced: boolean) => void;
  // Keyboard Navigation
  enableKeyboardNavigation: () => void;
  disableKeyboardNavigation: () => void;
  setKeyboardFocus: (element: string | null) => void;

  // Utilities
  resetToDefaults: () => void;
  exportUISettings: () => void;
  importUISettings: (settings: Partial<UIState>) => void;
  cleanupStore: () => void;
}

export interface UIStore extends UIState {
  actions: UIActions;
}

// Default state
const DEFAULT_STATE: UIState = {
  tabs: {
    activeTab: "conversations",
    tabHistory: ["conversations"],
    canGoBack: false,
    canGoForward: false,
  },

  panels: {
    leftWidth: 280,
    leftPanel: "folders",
    rightPanel: "conversations",
    selectedConversationId: null,
  },

  view: {
    viewMode: "grid",
    itemsPerPage: 20,
    sortColumn: "created_at",
    sortDirection: "desc",
    compactMode: false,
    showPreview: true,
  },

  modals: {
    activeModal: null,
    modalData: {},
    modalHistory: [],
  },

  sidebar: {
    isCollapsed: false,
    width: 280,
    pinnedSections: new Set(["folders", "recent"]),
    expandedSections: new Set(["folders", "recent", "analytics"]),
    showFolderPanel: false,
    activeFolderId: null,
  },

  bulkActions: {
    isEnabled: false,
    selectedItems: new Set(),
    availableActions: [],
    activeAction: null,
  },

  notifications: {
    toasts: [],
    banners: [],
  },

  loading: {
    global: false,
    sections: {},
    operations: {},
  },

  theme: {
    theme: "system",
    accentColor: "#0095ff",
    fontSize: "medium",
    animations: true,
    reducedMotion: false,
  },

  keyboardNavigation: {
    enabled: false,
    currentFocus: null,
    focusHistory: [],
  },
};

// Global timer manager for hover effects
const hoverTimers = new Map<string, NodeJS.Timeout>();

const setHoverTimer = (
  key: string,
  callback: () => void,
  delay: number,
): void => {
  clearHoverTimer(key);
  const timer = setTimeout(callback, delay);
  hoverTimers.set(key, timer);
};

const clearHoverTimer = (key: string): void => {
  const timer = hoverTimers.get(key);
  if (timer) {
    clearTimeout(timer);
    hoverTimers.delete(key);
  }
};

const clearAllHoverTimers = (): void => {
  hoverTimers.forEach((timer) => clearTimeout(timer));
  hoverTimers.clear();
};

// Store Implementation
export const useUIStore = create<UIStore>()(
  devtools(
    subscribeWithSelector(
      persist(
        (set, get) => ({
          ...DEFAULT_STATE,

          actions: {
            // ===========================
            // Tab Management
            // ===========================

            setActiveTab: (tab) => {
              set((state) => {
                const history = [...state.tabs.tabHistory];
                const currentIndex = history.length - 1;

                // Remove forward history if navigating to new tab
                history.splice(currentIndex + 1);

                // Add new tab if different from current
                if (tab !== state.tabs.activeTab) {
                  history.push(tab);
                }

                return {
                  tabs: {
                    activeTab: tab,
                    tabHistory: history,
                    canGoBack: history.length > 1,
                    canGoForward: false,
                  },
                };
              });
            },

            navigateBack: () => {
              set((state) => {
                const history = [...state.tabs.tabHistory];
                const currentIndex = history.findIndex(
                  (tab) => tab === state.tabs.activeTab,
                );

                if (currentIndex > 0) {
                  const previousTab = history[
                    currentIndex - 1
                  ] as TabState["activeTab"];

                  return {
                    tabs: {
                      ...state.tabs,
                      activeTab: previousTab,
                      canGoBack: currentIndex > 1,
                      canGoForward: true,
                    },
                  };
                }

                return state;
              });
            },

            navigateForward: () => {
              set((state) => {
                const history = [...state.tabs.tabHistory];
                const currentIndex = history.findIndex(
                  (tab) => tab === state.tabs.activeTab,
                );

                if (currentIndex < history.length - 1) {
                  const nextTab = history[
                    currentIndex + 1
                  ] as TabState["activeTab"];

                  return {
                    tabs: {
                      ...state.tabs,
                      activeTab: nextTab,
                      canGoBack: true,
                      canGoForward: currentIndex < history.length - 2,
                    },
                  };
                }

                return state;
              });
            },

            // ===========================
            // Panel Management
            // ===========================

            setPanelWidth: (width) => {
              set((state) => ({
                panels: {
                  ...state.panels,
                  leftWidth: Math.max(200, Math.min(500, width)),
                },
              }));
            },

            setLeftPanel: (panel) => {
              set((state) => ({
                panels: {
                  ...state.panels,
                  leftPanel: panel,
                },
              }));
            },

            setRightPanel: (panel) => {
              set((state) => ({
                panels: {
                  ...state.panels,
                  rightPanel: panel,
                },
              }));
            },

            selectConversation: (id) => {
              set((state) => ({
                panels: {
                  ...state.panels,
                  selectedConversationId: id,
                  rightPanel: id ? "editor" : "conversations",
                },
              }));
            },

            // ===========================
            // View Management
            // ===========================

            setViewMode: (mode) => {
              set((state) => ({
                view: {
                  ...state.view,
                  viewMode: mode,
                },
              }));
            },

            setItemsPerPage: (count) => {
              set((state) => ({
                view: {
                  ...state.view,
                  itemsPerPage: count,
                },
              }));
            },

            setSorting: (column, direction) => {
              set((state) => ({
                view: {
                  ...state.view,
                  sortColumn: column,
                  sortDirection: direction,
                },
              }));
            },

            toggleCompactMode: () => {
              set((state) => ({
                view: {
                  ...state.view,
                  compactMode: !state.view.compactMode,
                },
              }));
            },

            togglePreview: () => {
              set((state) => ({
                view: {
                  ...state.view,
                  showPreview: !state.view.showPreview,
                },
              }));
            },

            // ===========================
            // Modal Management
            // ===========================

            openModal: (modalId, data = {}) => {
              set((state) => ({
                modals: {
                  activeModal: modalId,
                  modalData: data,
                  modalHistory: [...state.modals.modalHistory, modalId],
                },
              }));
            },

            closeModal: () => {
              set((state) => ({
                modals: {
                  ...state.modals,
                  activeModal: null,
                  modalData: {},
                },
              }));
            },

            closeAllModals: () => {
              set(() => ({
                modals: {
                  activeModal: null,
                  modalData: {},
                  modalHistory: [],
                },
              }));
            },

            // ===========================
            // Sidebar Management
            // ===========================

            toggleSidebar: () => {
              set((state) => ({
                sidebar: {
                  ...state.sidebar,
                  isCollapsed: !state.sidebar.isCollapsed,
                },
              }));
            },

            setSidebarWidth: (width) => {
              set((state) => ({
                sidebar: {
                  ...state.sidebar,
                  width: Math.max(
                    MIN_SIDEBAR_WIDTH,
                    Math.min(MAX_SIDEBAR_WIDTH, width),
                  ),
                },
              }));
            },

            toggleSidebarSection: (sectionId) => {
              set((state) => {
                const expandedSections = new Set(
                  state.sidebar.expandedSections,
                );

                if (expandedSections.has(sectionId)) {
                  expandedSections.delete(sectionId);
                } else {
                  expandedSections.add(sectionId);
                }

                return {
                  sidebar: {
                    ...state.sidebar,
                    expandedSections,
                  },
                };
              });
            },

            pinSidebarSection: (sectionId, pinned) => {
              set((state) => {
                const pinnedSections = new Set(state.sidebar.pinnedSections);

                if (pinned) {
                  pinnedSections.add(sectionId);
                } else {
                  pinnedSections.delete(sectionId);
                }

                return {
                  sidebar: {
                    ...state.sidebar,
                    pinnedSections,
                  },
                };
              });
            },

            openFolderPanel: () => {
              set((state) => ({
                sidebar: {
                  ...state.sidebar,
                  showFolderPanel: true,
                },
              }));
            },

            closeFolderPanel: () => {
              set((state) => ({
                sidebar: {
                  ...state.sidebar,
                  showFolderPanel: false,
                },
              }));
            },

            toggleFolderPanel: () => {
              set((state) => ({
                sidebar: {
                  ...state.sidebar,
                  showFolderPanel: !state.sidebar.showFolderPanel,
                },
              }));
            },

            setActiveFolder: (folderId) => {
              set((state) => ({
                sidebar: {
                  ...state.sidebar,
                  activeFolderId: folderId,
                },
              }));
            },

            openFolderPanelHover: () => {
              const state = get();

              // If panel is already open, just clear close timer
              if (state.sidebar.showFolderPanel) {
                clearHoverTimer("closeFolderPanel");
                return;
              }

              // Clear any existing timers
              clearHoverTimer("closeFolderPanel");
              clearHoverTimer("openFolderPanel");

              // Set timer to open panel after 80ms
              setHoverTimer(
                "openFolderPanel",
                () => {
                  set((state) => ({
                    sidebar: {
                      ...state.sidebar,
                      showFolderPanel: true,
                    },
                  }));
                },
                80,
              );
            },

            closeFolderPanelHover: () => {
              const state = get();

              // If panel is not open, just clear open timer
              if (!state.sidebar.showFolderPanel) {
                clearHoverTimer("openFolderPanel");
                return;
              }

              // Clear any existing timers
              clearHoverTimer("openFolderPanel");
              clearHoverTimer("closeFolderPanel");

              // Set timer to close panel after 150ms (longer delay for stability)
              setHoverTimer(
                "closeFolderPanel",
                () => {
                  set((state) => ({
                    sidebar: {
                      ...state.sidebar,
                      showFolderPanel: false,
                    },
                  }));
                },
                150,
              );
            },

            clearHoverTimers: () => {
              clearHoverTimer("openFolderPanel");
              clearHoverTimer("closeFolderPanel");
            },

            // ===========================
            // Bulk Actions
            // ===========================

            enableBulkActions: (actions) => {
              set({
                bulkActions: {
                  isEnabled: true,
                  selectedItems: new Set(),
                  availableActions: actions,
                  activeAction: null,
                },
              });
            },

            disableBulkActions: () => {
              set({
                bulkActions: {
                  isEnabled: false,
                  selectedItems: new Set(),
                  availableActions: [],
                  activeAction: null,
                },
              });
            },

            selectBulkItem: (itemId, selected) => {
              set((state) => {
                const selectedItems = new Set(state.bulkActions.selectedItems);

                if (selected) {
                  selectedItems.add(itemId);
                } else {
                  selectedItems.delete(itemId);
                }

                return {
                  bulkActions: {
                    ...state.bulkActions,
                    selectedItems,
                  },
                };
              });
            },

            selectAllBulkItems: (items, selected) => {
              set((state) => ({
                bulkActions: {
                  ...state.bulkActions,
                  selectedItems: selected ? new Set(items) : new Set(),
                },
              }));
            },

            clearBulkSelection: () => {
              set((state) => ({
                bulkActions: {
                  ...state.bulkActions,
                  selectedItems: new Set(),
                },
              }));
            },

            setBulkAction: (action) => {
              set((state) => ({
                bulkActions: {
                  ...state.bulkActions,
                  activeAction: action,
                },
              }));
            },

            // ===========================
            // Notification Management
            // ===========================

            showToast: (toast) => {
              const id = `toast-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

              set((state) => ({
                notifications: {
                  ...state.notifications,
                  toasts: [...state.notifications.toasts, { ...toast, id }],
                },
              }));

              // Auto-remove toast after duration
              if (toast.duration !== 0) {
                setTimeout(() => {
                  get().actions.hideToast(id);
                }, toast.duration || 5000);
              }

              return id;
            },

            hideToast: (id) => {
              set((state) => ({
                notifications: {
                  ...state.notifications,
                  toasts: state.notifications.toasts.filter(
                    (toast) => toast.id !== id,
                  ),
                },
              }));
            },

            clearToasts: () => {
              set((state) => ({
                notifications: {
                  ...state.notifications,
                  toasts: [],
                },
              }));
            },

            showBanner: (banner) => {
              const id = `banner-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

              set((state) => ({
                notifications: {
                  ...state.notifications,
                  banners: [...state.notifications.banners, { ...banner, id }],
                },
              }));

              return id;
            },

            hideBanner: (id) => {
              set((state) => ({
                notifications: {
                  ...state.notifications,
                  banners: state.notifications.banners.filter(
                    (banner) => banner.id !== id,
                  ),
                },
              }));
            },

            clearBanners: () => {
              set((state) => ({
                notifications: {
                  ...state.notifications,
                  banners: [],
                },
              }));
            },

            // ===========================
            // Loading States
            // ===========================

            setGlobalLoading: (loading) => {
              set((state) => ({
                loading: {
                  ...state.loading,
                  global: loading,
                },
              }));
            },

            setSectionLoading: (section, loading) => {
              set((state) => ({
                loading: {
                  ...state.loading,
                  sections: {
                    ...state.loading.sections,
                    [section]: loading,
                  },
                },
              }));
            },

            setOperationLoading: (operation, loading) => {
              set((state) => ({
                loading: {
                  ...state.loading,
                  operations: {
                    ...state.loading.operations,
                    [operation]: loading,
                  },
                },
              }));
            },

            clearAllLoading: () => {
              set({
                loading: {
                  global: false,
                  sections: {},
                  operations: {},
                },
              });
            },

            // ===========================
            // Theme Management
            // ===========================

            setTheme: (theme) => {
              set((state) => ({
                theme: {
                  ...state.theme,
                  theme,
                },
              }));
            },

            setAccentColor: (color) => {
              set((state) => ({
                theme: {
                  ...state.theme,
                  accentColor: color,
                },
              }));
            },

            setFontSize: (size) => {
              set((state) => ({
                theme: {
                  ...state.theme,
                  fontSize: size,
                },
              }));
            },

            toggleAnimations: () => {
              set((state) => ({
                theme: {
                  ...state.theme,
                  animations: !state.theme.animations,
                },
              }));
            },

            setReducedMotion: (reduced) => {
              set((state) => ({
                theme: {
                  ...state.theme,
                  reducedMotion: reduced,
                },
              }));
            },
            // ===========================
            // Keyboard Navigation
            // ===========================

            enableKeyboardNavigation: () => {
              set((state) => ({
                keyboardNavigation: {
                  ...state.keyboardNavigation,
                  enabled: true,
                },
              }));
            },

            disableKeyboardNavigation: () => {
              set((state) => ({
                keyboardNavigation: {
                  ...state.keyboardNavigation,
                  enabled: false,
                  currentFocus: null,
                },
              }));
            },

            setKeyboardFocus: (element) => {
              set((state) => {
                const focusHistory = [...state.keyboardNavigation.focusHistory];

                if (
                  element &&
                  element !== state.keyboardNavigation.currentFocus
                ) {
                  focusHistory.push(element);

                  // Limit history to 10 items
                  if (focusHistory.length > 10) {
                    focusHistory.shift();
                  }
                }

                return {
                  keyboardNavigation: {
                    ...state.keyboardNavigation,
                    currentFocus: element,
                    focusHistory,
                  },
                };
              });
            },

            // ===========================
            // Utilities
            // ===========================

            resetToDefaults: () => {
              set(DEFAULT_STATE);
            },

            exportUISettings: () => {
              const state = get();

              const settings = {
                view: state.view,
                sidebar: {
                  ...state.sidebar,
                  pinnedSections: Array.from(state.sidebar.pinnedSections),
                  expandedSections: Array.from(state.sidebar.expandedSections),
                },
                theme: state.theme,
              };

              // Check if we're in a browser environment to prevent SSR errors
              if (typeof document !== "undefined") {
                const blob = new Blob([JSON.stringify(settings, null, 2)], {
                  type: "application/json",
                });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = `feedme-ui-settings-${Date.now()}.json`;
                link.click();
                URL.revokeObjectURL(url);
              }
            },

            importUISettings: (settings) => {
              set((state) => ({
                ...state,
                ...settings,
                // Convert arrays back to Sets for sidebar sections
                ...(settings.sidebar && {
                  sidebar: {
                    ...state.sidebar,
                    ...settings.sidebar,
                    pinnedSections: new Set(
                      settings.sidebar.pinnedSections || [],
                    ),
                    expandedSections: new Set(
                      settings.sidebar.expandedSections || [],
                    ),
                  },
                }),
              }));
            },

            cleanupStore: () => {
              clearAllHoverTimers();
            },
          },
        }),
        {
          name: "feedme-ui-store",
          partialize: (state) => ({
            view: state.view,
            panels: state.panels,
            sidebar: {
              ...state.sidebar,
              pinnedSections: Array.from(state.sidebar.pinnedSections),
              expandedSections: Array.from(state.sidebar.expandedSections),
              // Note: hoverTimers are excluded from persistence (not persisted)
            },
            theme: state.theme,
          }),
        },
      ),
    ),
    {
      name: "feedme-ui-store",
    },
  ),
);

// Convenience hooks
export const useUITabs = () => useUIStore((state) => state.tabs);
export const useUIPanels = () => useUIStore((state) => state.panels);
export const useUIView = () => useUIStore((state) => state.view);
export const useUIModals = () => useUIStore((state) => state.modals);
export const useUISidebar = () => useUIStore((state) => state.sidebar);
export const useUIBulkActions = () => useUIStore((state) => state.bulkActions);
export const useUINotifications = () =>
  useUIStore((state) => state.notifications);
export const useUILoading = () => useUIStore((state) => state.loading);
export const useUITheme = () => useUIStore((state) => state.theme);
export const useUIKeyboard = () =>
  useUIStore((state) => state.keyboardNavigation);
export const useUIActions = () => useUIStore((state) => state.actions);

// Keep reduced motion preferences in sync with OS setting.
if (typeof window !== "undefined") {
  const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const handleMotionChange = (event: MediaQueryListEvent) => {
    useUIStore.getState().actions.setReducedMotion(event.matches);
  };

  useUIStore.getState().actions.setReducedMotion(mediaQuery.matches);
  mediaQuery.addEventListener("change", handleMotionChange);
}
