'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useAgent } from '@/features/librechat/AgentContext';
import { PanelLeftClose, PanelLeft, ChevronDown, Settings, Check, Layers } from 'lucide-react';
import { SettingsDialogV2 } from '@/features/settings/components/SettingsDialogV2';
import { useArtifactActions, useArtifactSelector } from '@/features/librechat/artifacts';
import { modelsAPI, PROVIDER_LABELS, type ModelTier, type Provider as ProviderId } from '@/services/api/endpoints/models';

interface HeaderProps {
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
}

interface AgentState {
  model?: string;
  provider?: string;
  [key: string]: unknown;
}

// Hierarchical provider -> models structure
interface ModelInfo {
  readonly id: string;
  readonly name: string;
}

interface ProviderInfo {
  readonly id: string;
  readonly name: string;
  readonly icon: string;
  readonly models: readonly ModelInfo[];
}

const FALLBACK_PROVIDERS: ProviderInfo[] = [
  {
    id: 'google',
    name: 'Gemini',
    icon: '/icons/google.svg',
    models: [
      { id: 'gemini-3-flash-preview', name: 'Gemini 3.0 Flash' },
      { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
      { id: 'gemini-3-pro-preview', name: 'Gemini 3.0 Pro' },
    ],
  },
  {
    id: 'xai',
    name: 'Grok',
    icon: '/icons/xai.svg',
    models: [
      { id: 'grok-4-1-fast-reasoning', name: 'Grok 4.1 Fast' },
    ],
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    icon: '/icons/openrouter.svg',
    models: [
      { id: 'x-ai/grok-4.1-fast', name: 'Grok 4.1 Fast' },
      { id: 'minimax/minimax-m2.1', name: 'MiniMax M2.1' },
    ],
  },
];

// Helper to find model info from nested structure
function findModelInfo(
  modelId: string,
  providers: readonly ProviderInfo[]
): { model: ModelInfo; provider: ProviderInfo } | null {
  for (const provider of providers) {
    const model = provider.models.find((m) => m.id === modelId);
    if (model) {
      return { model, provider };
    }
  }
  return null;
}

const PROVIDER_ICONS: Record<ProviderId, string> = {
  google: '/icons/google.svg',
  xai: '/icons/xai.svg',
  openrouter: '/icons/openrouter.svg',
};

const TIER_ORDER: Record<ModelTier, number> = { pro: 0, standard: 1, lite: 2 };

export function Header({ onToggleSidebar, sidebarOpen }: HeaderProps) {
  const { agent, resolvedModel } = useAgent();
  const orderedIds = useArtifactSelector((s) => s.orderedIds);
  const isArtifactsVisible = useArtifactSelector((s) => s.isArtifactsVisible);
  const currentArtifactId = useArtifactSelector((s) => s.currentArtifactId);
  const { setArtifactsVisible, setCurrentArtifact } = useArtifactActions();
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [activeProviderId, setActiveProviderId] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const providerButtonRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const modelButtonRefs = useRef<Record<string, Array<HTMLButtonElement | null>>>({});
  const [providers, setProviders] = useState<ProviderInfo[]>(FALLBACK_PROVIDERS);

  const agentState = agent?.state as AgentState | undefined;
  const currentModel = resolvedModel || agentState?.model || 'gemini-3-flash-preview';
  const currentModelData = findModelInfo(currentModel, providers);
  const currentModelName = currentModelData?.model.name || modelsAPI.getDisplayName(currentModel);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const config = await modelsAPI.getConfig();
        const providerOrder: ProviderId[] = ['google', 'xai', 'openrouter'];

        const nextProviders: ProviderInfo[] = providerOrder
          .filter((id) => Boolean(config.available_providers[id]))
          .map((id) => {
            const models = Object.entries(config.models)
              .filter(([, info]) => info.provider === id)
              .sort((a, b) => {
                const tierA = TIER_ORDER[a[1].tier];
                const tierB = TIER_ORDER[b[1].tier];
                if (tierA !== tierB) return tierA - tierB;
                return a[1].display_name.localeCompare(b[1].display_name);
              })
              .map(([modelId, info]) => ({ id: modelId, name: info.display_name }));

            return {
              id,
              name: PROVIDER_LABELS[id] || id,
              icon: PROVIDER_ICONS[id],
              models,
            };
          })
          .filter((p) => p.models.length > 0);

        if (!cancelled && nextProviders.length > 0) {
          setProviders(nextProviders);
        }
      } catch {
        // Keep fallback providers.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const closeDropdown = useCallback((returnFocus = false) => {
    setShowModelDropdown(false);
    setActiveProviderId(null);
    if (returnFocus) {
      requestAnimationFrame(() => {
        triggerRef.current?.focus();
      });
    }
  }, []);

  const focusProviderByIndex = useCallback((index: number) => {
    const count = providers.length;
    if (!count) return;
    const nextIndex = (index + count) % count;
    providerButtonRefs.current[nextIndex]?.focus();
  }, [providers.length]);

  const focusProviderById = useCallback((providerId: string | null) => {
    if (!providerId) return;
    const index = providers.findIndex((provider) => provider.id === providerId);
    if (index >= 0) {
      providerButtonRefs.current[index]?.focus();
    }
  }, [providers]);

  const focusModelByIndex = useCallback((providerId: string, index: number) => {
    const models = modelButtonRefs.current[providerId] ?? [];
    const count = models.length;
    if (!count) return;
    const nextIndex = (index + count) % count;
    models[nextIndex]?.focus();
  }, []);

  const focusFirstModel = useCallback((providerId: string) => {
    requestAnimationFrame(() => {
      const models = modelButtonRefs.current[providerId] ?? [];
      const firstModel = models.find(Boolean);
      firstModel?.focus();
    });
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!showModelDropdown) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target;
      if (!target || !(target instanceof Node)) return;
      if (dropdownRef.current && !dropdownRef.current.contains(target)) {
        closeDropdown();
      }
    };

    // Use capture phase to catch all clicks
    document.addEventListener('mousedown', handleClickOutside, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside, true);
    };
  }, [closeDropdown, showModelDropdown]);

  // Close dropdown on escape key
  useEffect(() => {
    if (!showModelDropdown) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeDropdown(true);
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [closeDropdown, showModelDropdown]);

  const handleModelSelect = useCallback(
    (modelId: string, providerId: string, options?: { returnFocus?: boolean }) => {
      if (agent) {
        agent.setState({
          ...agent.state,
          model: modelId,
          provider: providerId,
        });
      }
      closeDropdown(options?.returnFocus);
    },
    [agent, closeDropdown]
  );


  const handleArtifactToggle = useCallback(() => {
    if (orderedIds.length === 0) return;

    if (isArtifactsVisible) {
      setArtifactsVisible(false);
      return;
    }

    if (!currentArtifactId) {
      setCurrentArtifact(orderedIds[orderedIds.length - 1]);
    }
    setArtifactsVisible(true);
  }, [
    orderedIds,
    isArtifactsVisible,
    currentArtifactId,
    setArtifactsVisible,
    setCurrentArtifact,
  ]);

  const handleProviderKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>, providerIndex: number, providerId: string) => {
      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          focusProviderByIndex(providerIndex + 1);
          break;
        case 'ArrowUp':
          event.preventDefault();
          focusProviderByIndex(providerIndex - 1);
          break;
        case 'Home':
          event.preventDefault();
          focusProviderByIndex(0);
          break;
        case 'End':
          event.preventDefault();
          focusProviderByIndex(providers.length - 1);
          break;
        case 'ArrowRight':
        case 'Enter':
        case ' ':
          event.preventDefault();
          setActiveProviderId(providerId);
          focusFirstModel(providerId);
          break;
        case 'ArrowLeft':
          event.preventDefault();
          setActiveProviderId(null);
          break;
        case 'Escape':
          event.preventDefault();
          closeDropdown(true);
          break;
        default:
          break;
      }
    },
    [closeDropdown, focusFirstModel, focusProviderByIndex, providers.length]
  );

  const handleModelKeyDown = useCallback(
    (
      event: React.KeyboardEvent<HTMLButtonElement>,
      providerId: string,
      modelIndex: number,
      modelId: string
    ) => {
      const modelCount = modelButtonRefs.current[providerId]?.length ?? 0;
      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          focusModelByIndex(providerId, modelIndex + 1);
          break;
        case 'ArrowUp':
          event.preventDefault();
          focusModelByIndex(providerId, modelIndex - 1);
          break;
        case 'Home':
          event.preventDefault();
          focusModelByIndex(providerId, 0);
          break;
        case 'End':
          event.preventDefault();
          if (modelCount > 0) {
            focusModelByIndex(providerId, modelCount - 1);
          }
          break;
        case 'ArrowLeft':
          event.preventDefault();
          focusProviderById(providerId);
          setActiveProviderId(providerId);
          break;
        case 'Escape':
          event.preventDefault();
          closeDropdown(true);
          break;
        case 'Enter':
        case ' ':
          event.preventDefault();
          handleModelSelect(modelId, providerId, { returnFocus: true });
          break;
        default:
          break;
      }
    },
    [closeDropdown, focusModelByIndex, focusProviderById, handleModelSelect]
  );

  return (
    <header className="lc-header">
      <div className="lc-header-left">
        {/* Toggle sidebar button */}
        <button
          className="lc-toggle-sidebar-btn"
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          aria-expanded={sidebarOpen}
        >
          {sidebarOpen ? <PanelLeftClose size={20} /> : <PanelLeft size={20} />}
        </button>

        {/* Model selector */}
        <div ref={dropdownRef} style={{ position: 'relative' }}>
          <button
            className="lc-model-selector"
            ref={triggerRef}
            onClick={() => {
              const next = !showModelDropdown;
              setShowModelDropdown(next);

              if (!next) {
                setActiveProviderId(null);
                return;
              }

              const selectedProviderId =
                currentModelData?.provider.id ?? providers[0]?.id ?? null;
              setActiveProviderId(selectedProviderId);
              if (selectedProviderId) {
                requestAnimationFrame(() => {
                  focusProviderById(selectedProviderId);
                });
              }
            }}
            aria-haspopup="menu"
            aria-expanded={showModelDropdown}
            aria-label={`Current model: ${currentModelName}. Click to change.`}
          >
            <span>{currentModelName}</span>
            <ChevronDown size={16} style={{ transform: showModelDropdown ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s ease' }} />
          </button>

          {showModelDropdown && (
            <div
              className="lc-model-dropdown"
              role="menu"
              aria-label="Select model provider"
            >
              {providers.map((provider, providerIndex) => (
                <div
                  key={provider.id}
                  className="lc-provider-item-wrapper"
                  onMouseEnter={() => setActiveProviderId(provider.id)}
                >
                  <button
                    ref={(node) => {
                      providerButtonRefs.current[providerIndex] = node;
                    }}
                    className={`lc-provider-item ${activeProviderId === provider.id ? 'active' : ''} ${currentModelData?.provider.id === provider.id ? 'has-selected' : ''}`}
                    onClick={() => setActiveProviderId(activeProviderId === provider.id ? null : provider.id)}
                    onFocus={() => setActiveProviderId(provider.id)}
                    onKeyDown={(event) => handleProviderKeyDown(event, providerIndex, provider.id)}
                    role="menuitem"
                    aria-haspopup="menu"
                    aria-expanded={activeProviderId === provider.id}
                    aria-controls={`provider-models-${provider.id}`}
                  >
                    <span className="lc-provider-item-left">
                      <img
                        src={provider.icon}
                        alt=""
                        className="lc-provider-icon"
                        aria-hidden="true"
                      />
                      <span>{provider.name}</span>
                    </span>
                    <ChevronDown
                      size={14}
                      style={{
                        transform: 'rotate(-90deg)',
                        color: 'var(--lc-text-tertiary)',
                      }}
                    />
                  </button>

                  {/* Sub-dropdown for models */}
                  {activeProviderId === provider.id && (
                    <div
                      className="lc-model-sub-dropdown"
                      id={`provider-models-${provider.id}`}
                      role="menu"
                      aria-label={`Models for ${provider.name}`}
                    >
                      {provider.models.map((model, modelIndex) => (
                        <button
                          key={model.id}
                          ref={(node) => {
                            if (!modelButtonRefs.current[provider.id]) {
                              modelButtonRefs.current[provider.id] = [];
                            }
                            modelButtonRefs.current[provider.id][modelIndex] = node;
                          }}
                          className={`lc-model-option ${model.id === currentModel ? 'selected' : ''}`}
                          onClick={() => handleModelSelect(model.id, provider.id)}
                          onKeyDown={(event) =>
                            handleModelKeyDown(event, provider.id, modelIndex, model.id)
                          }
                          role="menuitemradio"
                          aria-checked={model.id === currentModel}
                        >
                          <span>{model.name}</span>
                          {model.id === currentModel && (
                            <Check size={14} style={{ color: 'var(--lc-accent)' }} />
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="lc-header-right" style={{ display: 'flex', gap: '8px' }}>
        {orderedIds.length > 0 && (
          <button
            className="lc-toggle-sidebar-btn lc-artifact-toggle"
            onClick={handleArtifactToggle}
            aria-label={isArtifactsVisible ? 'Close artifacts panel' : 'Open artifacts panel'}
            aria-pressed={isArtifactsVisible}
            title="Artifacts"
          >
            <Layers size={18} />
            <span className="lc-artifact-count">{orderedIds.length}</span>
          </button>
        )}
        {/* FeedMe link */}
        <Link
          href="/feedme"
          className="lc-toggle-sidebar-btn"
          aria-label="Open FeedMe"
          title="FeedMe - Document Processing"
        >
          <img
            src="/feedme_icon.png"
            alt=""
            className="lc-feedme-icon"
            aria-hidden="true"
          />
        </Link>

        {/* Settings button */}
        <button
          className="lc-toggle-sidebar-btn"
          onClick={() => setShowSettings(true)}
          aria-label="Open settings"
        >
          <Settings size={18} />
        </button>
      </div>

      {/* Settings Dialog */}
      <SettingsDialogV2
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
      />
    </header>
  );
}

export default Header;
