'use client';

import React, { useState, useCallback, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useAgent } from '@/features/librechat/AgentContext';
import { PanelLeftClose, PanelLeft, ChevronDown, Settings, Check, Layers } from 'lucide-react';
import { SettingsDialogV2 } from '@/features/settings/components/SettingsDialogV2';
import { useArtifactActions, useArtifactSelector } from '@/features/librechat/artifacts';

interface HeaderProps {
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
}

interface AgentState {
  model?: string;
  provider?: string;
  [key: string]: unknown;
}

const MODELS = [
  { id: 'gemini-3-flash-preview', name: 'Gemini 3.0 Flash', provider: 'google' },
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'google' },
  { id: 'gemini-3-pro-preview', name: 'Gemini 3.0 Pro', provider: 'google' },
  { id: 'grok-4-1-fast-reasoning', name: 'Grok 4.1 Fast', provider: 'xai' },

];

export function Header({ onToggleSidebar, sidebarOpen }: HeaderProps) {
  const { agent, resolvedModel } = useAgent();
  const orderedIds = useArtifactSelector((s) => s.orderedIds);
  const isArtifactsVisible = useArtifactSelector((s) => s.isArtifactsVisible);
  const currentArtifactId = useArtifactSelector((s) => s.currentArtifactId);
  const { setArtifactsVisible, setCurrentArtifact } = useArtifactActions();
  const [showModelDropdown, setShowModelDropdown] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const agentState = agent?.state as AgentState | undefined;
  const currentModel = resolvedModel || agentState?.model || 'gemini-3-flash-preview';
  const currentModelInfo = MODELS.find((m) => m.id === currentModel) || MODELS[0];

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!showModelDropdown) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowModelDropdown(false);
      }
    };

    // Use capture phase to catch all clicks
    document.addEventListener('mousedown', handleClickOutside, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside, true);
    };
  }, [showModelDropdown]);

  // Close dropdown on escape key
  useEffect(() => {
    if (!showModelDropdown) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowModelDropdown(false);
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [showModelDropdown]);

  const handleModelSelect = useCallback(
    (modelId: string) => {
      const model = MODELS.find((m) => m.id === modelId);
      if (model && agent) {
        agent.setState({
          ...agent.state,
          model: model.id,
          provider: model.provider,
        });
      }
      setShowModelDropdown(false);
    },
    [agent]
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
            onClick={() => setShowModelDropdown(!showModelDropdown)}
            aria-haspopup="listbox"
            aria-expanded={showModelDropdown}
            aria-label={`Current model: ${currentModelInfo.name}. Click to change.`}
          >
            <span>{currentModelInfo.name}</span>
            <ChevronDown size={16} style={{ transform: showModelDropdown ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s ease' }} />
          </button>

          {showModelDropdown && (
            <div
              className="lc-model-dropdown"
              role="listbox"
              aria-label="Select model"
            >
              {MODELS.map((model) => (
                <button
                  key={model.id}
                  className={`lc-model-option ${model.id === currentModel ? 'selected' : ''}`}
                  onClick={() => handleModelSelect(model.id)}
                  role="option"
                  aria-selected={model.id === currentModel}
                >
                  <span>{model.name}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      style={{
                        fontSize: '11px',
                        color: 'var(--lc-text-tertiary)',
                        textTransform: 'uppercase',
                      }}
                    >
                      {model.provider}
                    </span>
                    {model.id === currentModel && <Check size={14} style={{ color: 'var(--lc-accent)' }} />}
                  </span>
                </button>
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
