"use client";

import React, {
  useCallback,
  useState,
  useRef,
  useEffect,
  ChangeEvent,
  useLayoutEffect,
  KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useAgent, type AgentMode } from "@/features/librechat/AgentContext";
import {
  ArrowUp,
  Command,
  MessageSquare,
  Zap,
  Plus,
  Check,
  ChevronRight,
  Paperclip,
  Globe,
  Sparkles,
  SquarePen,
} from "lucide-react";
import type { AttachmentInput } from "@/services/ag-ui/types";
import { AttachmentPreviewList } from "@/features/librechat/components/AttachmentPreview";
import { LayoutTextFlip } from "@/components/ui/layout-text-flip";
import { motion } from "motion/react";

interface LandingProps {
  onStarterClick?: (prompt: string) => void;
}

const ACTION_PILLS = [
  { icon: Zap, label: "Skills", action: "skills" },
  { icon: SquarePen, label: "Rephrase", action: "rephrase" },
  { icon: MessageSquare, label: "Reply", action: "reply" },
  { icon: Command, label: "Prompt", action: "prompt" },
];

const AGENT_MODE_LABELS: Record<AgentMode, string> = {
  general: "General Assistant",
  mailbird_expert: "Mailbird Expert",
  research_expert: "Research Expert",
  creative_expert: "Creative Expert",
};

const AGENT_MODE_OPTIONS: AgentMode[] = [
  "general",
  "mailbird_expert",
  "research_expert",
  "creative_expert",
];

type CommandMenuDirection = "down" | "up";

export function Landing({ onStarterClick }: LandingProps) {
  const {
    sendMessage,
    webSearchMode,
    setWebSearchMode,
    agentMode,
    setAgentMode,
  } = useAgent();
  const [inputValue, setInputValue] = useState("");
  const [attachments, setAttachments] = useState<AttachmentInput[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [isCommandMenuOpen, setCommandMenuOpen] = useState(false);
  const [isExpertSubmenuOpen, setExpertSubmenuOpen] = useState(false);
  const [commandMenuDirection, setCommandMenuDirection] =
    useState<CommandMenuDirection>("down");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const commandMenuRef = useRef<HTMLDivElement>(null);
  const commandTriggerRef = useRef<HTMLButtonElement>(null);
  const maxTextareaHeight = 200;

  const normalizePastedText = useCallback((value: string): string => {
    return value
      .replace(/\r\n?/g, "\n")
      .replace(/[\u2028\u2029]/g, "\n")
      .replace(
        /[\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000\u2007\u2060]/g,
        " ",
      )
      .replace(/[\u200B\u200C\u200D\uFEFF]/g, "");
  }, []);

  const resizeTextarea = useCallback(
    (target?: HTMLTextAreaElement | null) => {
      const textarea = target ?? textareaRef.current;
      if (!textarea) return;
      textarea.style.height = "auto";
      const scrollHeight = textarea.scrollHeight;
      const newHeight = Math.max(24, Math.min(scrollHeight, maxTextareaHeight));
      textarea.style.height = `${newHeight}px`;
      textarea.style.overflowY =
        scrollHeight > maxTextareaHeight ? "auto" : "hidden";
    },
    [maxTextareaHeight],
  );

  useLayoutEffect(() => {
    resizeTextarea();
  }, [inputValue, resizeTextarea]);

  const inferMimeType = useCallback((file: globalThis.File): string => {
    if (file.type) {
      const normalized = file.type.toLowerCase();
      if (normalized === "image/jpg" || normalized === "image/pjpeg") {
        return "image/jpeg";
      }
      if (normalized === "image/x-png") {
        return "image/png";
      }
      return normalized;
    }
    const lower = file.name.toLowerCase();
    if (lower.endsWith(".png")) return "image/png";
    if (
      lower.endsWith(".jpg") ||
      lower.endsWith(".jpeg") ||
      lower.endsWith(".jfif")
    )
      return "image/jpeg";
    if (lower.endsWith(".gif")) return "image/gif";
    if (lower.endsWith(".webp")) return "image/webp";
    if (lower.endsWith(".bmp")) return "image/bmp";
    if (lower.endsWith(".tif") || lower.endsWith(".tiff")) return "image/tiff";
    if (lower.endsWith(".heic")) return "image/heic";
    if (lower.endsWith(".heif")) return "image/heif";
    if (lower.endsWith(".avif")) return "image/avif";
    if (lower.endsWith(".svg")) return "image/svg+xml";
    if (lower.endsWith(".ico")) return "image/x-icon";
    if (lower.endsWith(".log")) return "text/plain";
    if (lower.endsWith(".txt")) return "text/plain";
    if (lower.endsWith(".md")) return "text/markdown";
    if (lower.endsWith(".csv")) return "text/csv";
    if (lower.endsWith(".json")) return "application/json";
    return "application/octet-stream";
  }, []);

  const handleFileSelect = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;

      const newAttachments: AttachmentInput[] = [];
      const errors: string[] = [];

      for (const file of Array.from(files)) {
        const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
        if (file.size > MAX_FILE_SIZE) {
          errors.push(`${file.name} exceeds 10MB limit`);
          continue;
        }

        try {
          const reader = new FileReader();
          const dataUrl = await new Promise<string>((resolve, reject) => {
            reader.onload = () => {
              if (typeof reader.result === "string") resolve(reader.result);
              else reject(new Error("Failed to read file"));
            };
            reader.onerror = () => reject(new Error("Read error"));
            reader.readAsDataURL(file);
          });

          newAttachments.push({
            name: file.name,
            mime_type: inferMimeType(file),
            data_url: dataUrl,
            size: file.size,
          });
        } catch (err) {
          console.error("File read error:", err);
        }
      }

      if (newAttachments.length > 0) {
        setAttachments((prev) => [...prev, ...newAttachments]);
      }
    },
    [inferMimeType],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      handleFileSelect(e.dataTransfer.files);
    },
    [handleFileSelect],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  useEffect(() => {
    if (!isCommandMenuOpen) return;

    const onPointerDown = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (commandMenuRef.current?.contains(target)) return;
      setCommandMenuOpen(false);
      setExpertSubmenuOpen(false);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setCommandMenuOpen(false);
      setExpertSubmenuOpen(false);
      commandTriggerRef.current?.focus();
    };

    document.addEventListener("mousedown", onPointerDown, true);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown, true);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isCommandMenuOpen]);

  const updateCommandMenuDirection = useCallback(() => {
    const trigger = commandTriggerRef.current;
    if (!trigger) return;

    const rect = trigger.getBoundingClientRect();
    const viewportHeight =
      window.innerHeight || document.documentElement.clientHeight;
    const estimatedMenuHeight = 300;
    const viewportPadding = 12;
    const spaceBelow = viewportHeight - rect.bottom - viewportPadding;
    const spaceAbove = rect.top - viewportPadding;
    const shouldOpenUp = spaceBelow < estimatedMenuHeight && spaceAbove > spaceBelow;
    setCommandMenuDirection(shouldOpenUp ? "up" : "down");
  }, []);

  useEffect(() => {
    if (!isCommandMenuOpen) return;

    const onViewportChange = () => updateCommandMenuDirection();
    window.addEventListener("resize", onViewportChange);
    window.addEventListener("scroll", onViewportChange, true);
    return () => {
      window.removeEventListener("resize", onViewportChange);
      window.removeEventListener("scroll", onViewportChange, true);
    };
  }, [isCommandMenuOpen, updateCommandMenuDirection]);

  const handleKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (inputValue.trim() || attachments.length > 0) {
          sendMessage(inputValue.trim(), attachments);
          setInputValue("");
          setAttachments([]);
          if (textareaRef.current) {
            textareaRef.current.style.height = "";
          }
        }
      }
    },
    [inputValue, attachments, sendMessage],
  );

  const handleSubmit = useCallback(() => {
    if (inputValue.trim() || attachments.length > 0) {
      sendMessage(inputValue.trim(), attachments);
      setInputValue("");
      setAttachments([]);
      if (textareaRef.current) {
        textareaRef.current.style.height = "";
      }
    }
  }, [inputValue, attachments, sendMessage]);

  const handleInputChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      setInputValue(e.target.value);
      resizeTextarea(e.currentTarget);
    },
    [resizeTextarea],
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const rawText =
        e.clipboardData?.getData("text/plain") ??
        e.clipboardData?.getData("text") ??
        "";
      if (!rawText) {
        requestAnimationFrame(() => resizeTextarea(e.currentTarget));
        return;
      }
      e.preventDefault();
      const normalized = normalizePastedText(rawText);
      const target = e.currentTarget;
      const start = target.selectionStart ?? inputValue.length;
      const end = target.selectionEnd ?? inputValue.length;
      const nextValue = `${inputValue.slice(0, start)}${normalized}${inputValue.slice(end)}`;
      setInputValue(nextValue);
      requestAnimationFrame(() => {
        const cursor = start + normalized.length;
        target.selectionStart = cursor;
        target.selectionEnd = cursor;
        resizeTextarea(target);
      });
    },
    [inputValue, normalizePastedText, resizeTextarea],
  );

  const openAttachmentPickerFromMenu = useCallback(() => {
    setCommandMenuOpen(false);
    setExpertSubmenuOpen(false);
    openFilePicker();
  }, [openFilePicker]);

  const toggleWebSearchMode = useCallback(() => {
    setWebSearchMode(webSearchMode === "on" ? "off" : "on");
  }, [setWebSearchMode, webSearchMode]);

  const selectAgentMode = useCallback(
    (mode: AgentMode) => {
      setAgentMode(mode);
      setCommandMenuOpen(false);
      setExpertSubmenuOpen(false);
    },
    [setAgentMode],
  );

  return (
    <div className="lc-landing">
      {/* Centered Content Container */}
      <div className="lc-landing-content">
        {/* Logo */}
        <div className="lc-landing-logo">
          <img src="/Sparrow_logo.png" alt="Agent Sparrow" />
        </div>

        <div>
          <motion.div className="relative mx-4 mt-4 mb-8 flex max-w-full flex-col items-center justify-center gap-3 text-center sm:mx-0 sm:flex-row sm:flex-wrap">
            <LayoutTextFlip
              text="What can I help you with?"
              words={[
                "Log files",
                "Images",
                "General questions",
                "Technical questions",
                "Writing articles",
              ]}
            />
          </motion.div>
        </div>

        <div className="lc-hero-search-container">
          <div
            className={`lc-hero-input-wrapper ${isDragOver ? "drag-over" : ""}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            {/* Attachment Preview Section */}
            {attachments.length > 0 && (
              <div className="px-3 pt-3">
                <AttachmentPreviewList
                  attachments={attachments}
                  onRemove={removeAttachment}
                  variant="input"
                />
              </div>
            )}

            <div className="flex items-center w-full">
              <div
                className="lc-command-menu-anchor"
                ref={commandMenuRef}
                onMouseLeave={() => setExpertSubmenuOpen(false)}
              >
                <button
                  ref={commandTriggerRef}
                  className={`lc-command-trigger ${isCommandMenuOpen ? "open" : ""}`}
                  onClick={() => {
                    setCommandMenuOpen((prev) => {
                      const nextOpen = !prev;
                      if (nextOpen) {
                        updateCommandMenuDirection();
                      } else {
                        setExpertSubmenuOpen(false);
                      }
                      return nextOpen;
                    });
                  }}
                  type="button"
                  aria-haspopup="menu"
                  aria-expanded={isCommandMenuOpen}
                  aria-label="Open composer tools"
                >
                  <Plus size={15} />
                </button>
                {isCommandMenuOpen && (
                  <div className={`lc-command-menu ${commandMenuDirection}`} role="menu">
                    <button
                      className="lc-command-item"
                      onClick={openAttachmentPickerFromMenu}
                      role="menuitem"
                      type="button"
                    >
                      <span className="lc-command-item-main">
                        <Paperclip size={15} className="lc-command-item-icon" />
                        <span>Add files or photos</span>
                      </span>
                    </button>
                    <button
                      className="lc-command-item lc-command-item-toggle"
                      onClick={toggleWebSearchMode}
                      role="menuitemcheckbox"
                      aria-checked={webSearchMode === "on"}
                      type="button"
                    >
                      <span className="lc-command-item-main">
                        <Globe size={15} className="lc-command-item-icon" />
                        <span>Web search</span>
                      </span>
                      <span className="lc-command-item-trailing">
                        <span
                          className={`lc-command-toggle ${webSearchMode === "on" ? "on" : "off"}`}
                          aria-hidden="true"
                        >
                          <span className="lc-command-toggle-thumb" />
                        </span>
                      </span>
                    </button>
                    <div className="lc-command-separator" aria-hidden="true" />
                    <div
                      className="lc-command-submenu-anchor"
                      onMouseEnter={() => setExpertSubmenuOpen(true)}
                    >
                      <button
                        className={`lc-command-item ${isExpertSubmenuOpen ? "active" : ""}`}
                        onClick={() => setExpertSubmenuOpen((prev) => !prev)}
                        role="menuitem"
                        aria-haspopup="menu"
                        aria-expanded={isExpertSubmenuOpen}
                        type="button"
                      >
                        <span className="lc-command-item-main">
                          <Sparkles size={15} className="lc-command-item-icon" />
                          <span className="lc-command-item-with-meta">
                            Expert mode
                            <small>{AGENT_MODE_LABELS[agentMode]}</small>
                          </span>
                        </span>
                        <ChevronRight size={14} />
                      </button>
                      {isExpertSubmenuOpen && (
                        <div
                          className={`lc-command-submenu ${commandMenuDirection}`}
                          role="menu"
                        >
                          {AGENT_MODE_OPTIONS.map((mode) => (
                            <button
                              key={mode}
                              className={`lc-command-item ${agentMode === mode ? "selected" : ""}`}
                              onClick={() => selectAgentMode(mode)}
                              role="menuitemradio"
                              aria-checked={agentMode === mode}
                              type="button"
                            >
                              <span>{AGENT_MODE_LABELS[mode]}</span>
                              {agentMode === mode && <Check size={14} />}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*,.png,.jpg,.jpeg,.jfif,.gif,.webp,.bmp,.tif,.tiff,.heic,.heif,.avif,.svg,.ico,.pdf,.txt,.log,.md,.json,.csv,text/plain"
                onChange={(e) => {
                  handleFileSelect(e.target.files);
                  e.target.value = "";
                }}
                style={{ display: "none" }}
              />

              <textarea
                ref={textareaRef}
                className="lc-hero-input flex-1"
                placeholder="Ask anything..."
                value={inputValue}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
                rows={1}
                wrap="soft"
                autoFocus
              />
              <div className="lc-hero-input-actions mr-1">
                <button
                  className="lc-hero-submit-btn"
                  onClick={handleSubmit}
                  disabled={!inputValue.trim() && attachments.length === 0}
                >
                  <ArrowUp size={16} />
                </button>
              </div>
            </div>
          </div>

          {/* Action Pills */}
          <div className="lc-hero-pills">
            {ACTION_PILLS.map((pill) => {
              const Icon = pill.icon;
              return (
                <button
                  key={pill.label}
                  className="lc-hero-pill"
                  onClick={() => {
                    // Placeholder for future actions
                  }}
                >
                  <Icon size={12} />
                  <span>{pill.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Landing;
