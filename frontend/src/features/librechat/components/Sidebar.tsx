'use client';

import React, { useState, useCallback, useRef, useEffect, memo } from 'react';
import type { User } from '@supabase/supabase-js';
import { Plus, MessageSquare, Trash2, MoreHorizontal, Pencil } from 'lucide-react';
import { useAuth } from '@/shared/contexts/AuthContext';

interface Conversation {
  id: string;
  title: string;
  timestamp?: Date;
}

interface SidebarProps {
  isOpen: boolean;
  isCollapsed: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  conversations: Conversation[];
  currentConversationId?: string;
  onSelectConversation: (id: string) => void;
  onRenameConversation?: (id: string, newTitle: string) => void;
  onDeleteConversation?: (id: string) => void;
}

const getUserDisplayName = (user: User | null): string => {
  if (!user) return 'Agent Sparrow';

  const meta = (user.user_metadata ?? {}) as Record<string, unknown>;
  const fullName = typeof meta.full_name === 'string' ? meta.full_name.trim() : '';
  const name = typeof meta.name === 'string' ? meta.name.trim() : '';

  if (fullName) return fullName;
  if (name) return name;

  const email = user.email?.trim();
  if (email) return email.split('@')[0] || email;

  return 'User';
};

const getUserAvatarUrl = (user: User | null): string => {
  if (!user) return '/Sparrow_logo_cropped.png';

  const meta = (user.user_metadata ?? {}) as Record<string, unknown>;
  const avatarUrl = typeof meta.avatar_url === 'string' ? meta.avatar_url.trim() : '';
  const pictureUrl = typeof meta.picture === 'string' ? meta.picture.trim() : '';

  return avatarUrl || pictureUrl || '/Sparrow_logo_cropped.png';
};

// Agent Sparrow Logo Component
const SparrowLogo = memo(function SparrowLogo() {
  return (
    <img
      src="/Sparrow_logo_cropped.png"
      alt="Agent Sparrow"
      className="lc-sidebar-avatar"
    />
  );
});

export function Sidebar({
  isOpen,
  isCollapsed,
  onToggle,
  onNewChat,
  conversations,
  currentConversationId,
  onSelectConversation,
  onRenameConversation,
  onDeleteConversation,
}: SidebarProps) {
  const { user } = useAuth();

  const userDisplayName = React.useMemo(() => getUserDisplayName(user), [user]);
  const userAvatarUrl = React.useMemo(() => getUserAvatarUrl(user), [user]);
  const [avatarSrc, setAvatarSrc] = useState<string>(userAvatarUrl);

  useEffect(() => {
    setAvatarSrc(userAvatarUrl);
  }, [userAvatarUrl]);

  // Group conversations by date
  const groupedConversations = React.useMemo(() => {
    const groups: Record<string, Conversation[]> = {
      Today: [],
      Yesterday: [],
      'Previous 7 Days': [],
      'Previous 30 Days': [],
      Older: [],
      Undated: [],
    };

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
    const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
    const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);

    for (const conv of conversations) {
      if (!conv.timestamp) {
        groups.Undated.push(conv);
        continue;
      }

      const date = conv.timestamp;
      if (date >= today) {
        groups.Today.push(conv);
      } else if (date >= yesterday) {
        groups.Yesterday.push(conv);
      } else if (date >= weekAgo) {
        groups['Previous 7 Days'].push(conv);
      } else if (date >= monthAgo) {
        groups['Previous 30 Days'].push(conv);
      } else {
        groups.Older.push(conv);
      }
    }

    return groups;
  }, [conversations]);

  if (!isOpen) {
    return null;
  }

  return (
    <aside className={`lc-sidebar ${isCollapsed ? 'collapsed' : ''}`} role="complementary" aria-label="Conversation sidebar">
      {/* Header with Logo and New Chat */}
      <div className="lc-sidebar-header">
        <div className="lc-sidebar-brand">
          <SparrowLogo />
          <span className="lc-sidebar-brand-text">Agent Sparrow</span>
        </div>
        <button
          className="lc-new-chat-btn"
          onClick={onNewChat}
          aria-label="Start new chat"
        >
          <Plus size={18} />
          <span>New Chat</span>
        </button>
      </div>

      {/* Conversation list */}
      <div className="lc-conversation-list" role="list" aria-label="Conversations">
        {Object.entries(groupedConversations).map(
          ([group, convs]) =>
            convs.length > 0 && (
              <div key={group} className="lc-date-group">
                <div className="lc-date-label">{group}</div>
                {convs.map((conv) => (
                  <ConversationItem
                    key={conv.id}
                    conversation={conv}
                    isActive={conv.id === currentConversationId}
                    onSelect={onSelectConversation}
                    onRename={onRenameConversation}
                    onDelete={onDeleteConversation}
                  />
                ))}
              </div>
            )
        )}

        {/* Empty state */}
        {conversations.length === 0 && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '32px 16px',
              color: 'var(--lc-text-tertiary)',
              textAlign: 'center',
            }}
          >
            <MessageSquare size={32} style={{ marginBottom: '12px', opacity: 0.5 }} />
            <p style={{ fontSize: '14px', margin: 0 }}>No conversations yet</p>
            <p style={{ fontSize: '12px', margin: '4px 0 0' }}>
              Start a new chat to begin
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div
        style={{
          padding: '12px',
          borderTop: '1px solid var(--lc-border-light)',
          marginTop: 'auto',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            padding: '8px 12px',
            borderRadius: '8px',
            cursor: 'pointer',
            color: 'var(--lc-text-secondary)',
            fontSize: '14px',
          }}
        >
          <img
            src={avatarSrc}
            alt={userDisplayName}
            onError={() => setAvatarSrc('/Sparrow_logo_cropped.png')}
            className="lc-sidebar-avatar"
          />
          <span>{userDisplayName}</span>
        </div>
      </div>
    </aside>
  );
}

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onSelect: (id: string) => void;
  onRename?: (id: string, newTitle: string) => void;
  onDelete?: (id: string) => void;
}

const ConversationItem = memo(function ConversationItem({
  conversation,
  isActive,
  onSelect,
  onRename,
  onDelete,
}: ConversationItemProps) {
  const [showMenu, setShowMenu] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(conversation.title);
  const [menuPosition, setMenuPosition] = useState<{ top: number; left: number } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    if (!menuOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside, true);
    };
  }, [menuOpen]);

  // Focus input when renaming
  useEffect(() => {
    if (isRenaming && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isRenaming]);

  const handleMenuClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();

    // Always calculate position when button exists (cheap operation)
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + 4,
        left: rect.right - 160, // 160px is min-width of menu
      });
    }

    setMenuOpen((prev) => !prev);
  }, []); // No dependencies - uses functional update and ref

  const handleRenameClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpen(false);
    setIsRenaming(true);
    setRenameValue(conversation.title);
  }, [conversation.title]);

  const handleDeleteClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setMenuOpen(false);
    if (onDelete) {
      onDelete(conversation.id);
    }
  }, [onDelete, conversation.id]);

  const handleRenameSubmit = useCallback((e?: React.FormEvent) => {
    e?.preventDefault();
    if (renameValue.trim() && renameValue !== conversation.title && onRename) {
      onRename(conversation.id, renameValue.trim());
    }
    setIsRenaming(false);
  }, [renameValue, conversation.id, conversation.title, onRename]);

  const handleRenameCancel = useCallback(() => {
    setIsRenaming(false);
    setRenameValue(conversation.title);
  }, [conversation.title]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      handleRenameCancel();
    } else if (e.key === 'Enter') {
      handleRenameSubmit();
    }
  }, [handleRenameCancel, handleRenameSubmit]);

  // Create stable click handler
  const handleClick = useCallback(() => {
    onSelect(conversation.id);
  }, [onSelect, conversation.id]);

  if (isRenaming) {
    return (
      <div
        className={`lc-conversation-item ${isActive ? 'active' : ''}`}
        style={{ position: 'relative' }}
        role="listitem"
      >
        <MessageSquare size={16} style={{ flexShrink: 0, opacity: 0.7 }} aria-hidden="true" />
        <input
          ref={inputRef}
          type="text"
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onBlur={handleRenameSubmit}
          onKeyDown={handleKeyDown}
          className="lc-rename-input"
          aria-label="Rename conversation"
        />
      </div>
    );
  }

  return (
    <div
      className={`lc-conversation-item ${isActive ? 'active' : ''}`}
      onClick={handleClick}
      onMouseEnter={() => setShowMenu(true)}
      onMouseLeave={() => {
        if (!menuOpen) setShowMenu(false);
      }}
      style={{ position: 'relative' }}
      role="listitem"
      aria-current={isActive ? 'page' : undefined}
    >
      <MessageSquare size={16} style={{ flexShrink: 0, opacity: 0.7 }} aria-hidden="true" />
      <span className="lc-conversation-title">
        {conversation.title}
      </span>

      {(showMenu || menuOpen) && (onRename || onDelete) && (
        <div ref={menuRef} style={{ position: 'absolute', right: '8px' }}>
          <button
            ref={buttonRef}
            onClick={handleMenuClick}
            className="lc-conversation-menu-btn"
            aria-label="Conversation options"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <MoreHorizontal size={16} />
          </button>

          {menuOpen && menuPosition && (
            <div
              className="lc-conversation-menu"
              role="menu"
              style={{
                top: menuPosition.top,
                left: menuPosition.left,
              }}
            >
              {onRename && (
                <button
                  onClick={handleRenameClick}
                  className="lc-conversation-menu-item"
                  role="menuitem"
                >
                  <Pencil size={14} />
                  <span>Rename</span>
                </button>
              )}
              {onDelete && (
                <button
                  onClick={handleDeleteClick}
                  className="lc-conversation-menu-item lc-conversation-menu-item-danger"
                  role="menuitem"
                >
                  <Trash2 size={14} />
                  <span>Delete</span>
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

export default Sidebar;
