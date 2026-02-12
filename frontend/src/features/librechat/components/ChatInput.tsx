"use client";

import React, {
  useState,
  useCallback,
  useRef,
  useEffect,
  useLayoutEffect,
  KeyboardEvent,
  ChangeEvent,
} from "react";
import { useAgent } from "@/features/librechat/AgentContext";
import { ArrowUp, Square, Paperclip } from "lucide-react";
import type { AttachmentInput } from "@/services/ag-ui/types";
import { toast } from "sonner";
import { AttachmentPreviewList } from "@/features/librechat/components/AttachmentPreview";

interface ChatInputProps {
  isLanding?: boolean;
  initialInput?: string;
  onInitialInputUsed?: () => void;
}

const LONG_RUN_SOFT_TIMEOUT_MS = 120_000;

export function ChatInput({
  initialInput,
  onInitialInputUsed,
  isLanding,
}: ChatInputProps) {
  const {
    sendMessage,
    isStreaming,
    abortRun,
    pendingPromptSteering,
    resolvePromptSteering,
    streamRecovery,
    webSearchMode,
    setWebSearchMode,
  } = useAgent();
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<AttachmentInput[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [steeringCountdownMs, setSteeringCountdownMs] = useState(0);
  const [retryCountdownMs, setRetryCountdownMs] = useState(0);
  const [softTimeoutVisible, setSoftTimeoutVisible] = useState(false);
  const [softTimeoutGeneration, setSoftTimeoutGeneration] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const lastAppliedInitialInputRef = useRef<string | null>(null);
  const readersRef = useRef<FileReader[]>([]);
  const isMountedRef = useRef(true);
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
  }, [input, resizeTextarea]);

  // Handle initial input from starters
  useEffect(() => {
    if (initialInput && initialInput !== lastAppliedInitialInputRef.current) {
      setInput(initialInput);
      lastAppliedInitialInputRef.current = initialInput;
      onInitialInputUsed?.();
      requestAnimationFrame(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
        }
      });
    }
  }, [initialInput, onInitialInputUsed]);

  // Abort any in-flight file reads on unmount to avoid leaks/state updates.
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      readersRef.current.forEach((reader) => {
        try {
          reader.abort();
        } catch {
          // ignore
        }
      });
      readersRef.current = [];
    };
  }, []);

  useEffect(() => {
    if (!pendingPromptSteering) {
      setSteeringCountdownMs(0);
      return;
    }
    const updateCountdown = () => {
      setSteeringCountdownMs(
        Math.max(0, pendingPromptSteering.expiresAt - Date.now()),
      );
    };
    updateCountdown();
    const intervalId = window.setInterval(updateCountdown, 200);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [pendingPromptSteering]);

  useEffect(() => {
    const nextRetryAt = streamRecovery.nextRetryAt;
    if (!streamRecovery.isRetrying || !nextRetryAt) {
      setRetryCountdownMs(0);
      return;
    }
    const updateCountdown = () => {
      setRetryCountdownMs(Math.max(0, nextRetryAt - Date.now()));
    };
    updateCountdown();
    const intervalId = window.setInterval(updateCountdown, 200);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [streamRecovery.isRetrying, streamRecovery.nextRetryAt]);

  useEffect(() => {
    if (!isStreaming) {
      setSoftTimeoutVisible(false);
      setSoftTimeoutGeneration(0);
      return;
    }
    const timeoutId = window.setTimeout(() => {
      setSoftTimeoutVisible(true);
    }, LONG_RUN_SOFT_TIMEOUT_MS);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [isStreaming, softTimeoutGeneration]);

  const handleSubmit = useCallback(async () => {
    if (!input.trim() && attachments.length === 0) return;

    const message = input.trim();
    const currentAttachments = [...attachments];

    setInput("");
    setAttachments([]);

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "";
    }

    await sendMessage(message, currentAttachments);
  }, [input, attachments, sendMessage]);

  const handleStop = useCallback(() => {
    abortRun();
  }, [abortRun]);

  const handleContinueLongRun = useCallback(() => {
    setSoftTimeoutVisible(false);
    setSoftTimeoutGeneration((prev) => prev + 1);
  }, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleInputChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      setInput(e.target.value);
      resizeTextarea(e.currentTarget);
    },
    [resizeTextarea],
  );

  const handleWebModeChange = useCallback(
    (e: ChangeEvent<HTMLSelectElement>) => {
      const nextMode = e.target.value === "on" ? "on" : "off";
      setWebSearchMode(nextMode);
    },
    [setWebSearchMode],
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
      const start = target.selectionStart ?? input.length;
      const end = target.selectionEnd ?? input.length;
      const nextValue = `${input.slice(0, start)}${normalized}${input.slice(end)}`;
      setInput(nextValue);

      requestAnimationFrame(() => {
        const cursor = start + normalized.length;
        target.selectionStart = cursor;
        target.selectionEnd = cursor;
        resizeTextarea(target);
      });
    },
    [input, normalizePastedText, resizeTextarea],
  );

  const handleFileSelect = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;

      const newAttachments: AttachmentInput[] = [];
      const errors: string[] = [];

      for (const file of Array.from(files)) {
        // Validate file size (max 10MB)
        const MAX_FILE_SIZE = 10 * 1024 * 1024;
        if (file.size > MAX_FILE_SIZE) {
          errors.push(`${file.name} exceeds 10MB limit`);
          continue;
        }

        const reader = new FileReader();
        try {
          // Read file as base64 with proper error handling
          readersRef.current.push(reader);
          const dataUrl = await new Promise<string>((resolve, reject) => {
            reader.onload = () => {
              if (typeof reader.result === "string") {
                resolve(reader.result);
              } else {
                reject(new Error("Failed to read file as string"));
              }
            };
            reader.onerror = () => {
              reject(
                new Error(
                  `Failed to read ${file.name}: ${reader.error?.message || "Unknown error"}`,
                ),
              );
            };
            reader.onabort = () => {
              reject(new Error(`Reading ${file.name} was aborted`));
            };
            reader.readAsDataURL(file);
          });

          newAttachments.push({
            name: file.name,
            mime_type: inferMimeType(file),
            data_url: dataUrl,
            size: file.size,
          });
        } catch (err) {
          const errorMessage =
            err instanceof Error ? err.message : `Failed to read ${file.name}`;
          errors.push(errorMessage);
          if (process.env.NODE_ENV !== "production") {
            console.error("File read error:", err);
          } else {
            console.error("File read failed");
          }
        } finally {
          readersRef.current = readersRef.current.filter((r) => r !== reader);
        }
      }

      if (!isMountedRef.current) return;

      if (newAttachments.length > 0) {
        setAttachments((prev) => [...prev, ...newAttachments]);
      }

      if (errors.length > 0) {
        const [first, ...rest] = errors;
        const description =
          rest.length > 0 ? `${first} (+${rest.length} more)` : first;
        toast.error("Some files could not be attached", { description });
      }
    },
    [inferMimeType],
  );

  const handleFileInputChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      handleFileSelect(e.target.files);
      e.target.value = ""; // Reset input
    },
    [handleFileSelect],
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

  const steeringSeconds = Math.max(0, Math.ceil(steeringCountdownMs / 1000));
  const retrySeconds = Math.max(0, Math.ceil(retryCountdownMs / 1000));

  return (
    <div
      className="lc-input-container"
      style={isLanding ? { display: "none" } : undefined}
      aria-hidden={isLanding ? "true" : undefined}
    >
      <div className="lc-input-wrapper">
        {(streamRecovery.isRetrying || streamRecovery.exhausted) && (
          <div className="lc-stream-recovery-banner" role="status" aria-live="polite">
            {streamRecovery.isRetrying ? (
              <>
                <strong>
                  Reconnecting ({streamRecovery.attemptsUsed}/{streamRecovery.maxRetries})
                </strong>
                <span>
                  Network interrupted. Retrying in {retrySeconds}s while preserving
                  partial response state.
                </span>
              </>
            ) : (
              <>
                <strong>Connection retries exhausted</strong>
                <span>
                  This response is marked limited and may be incomplete.
                </span>
              </>
            )}
          </div>
        )}

        {isStreaming && softTimeoutVisible && (
          <div className="lc-soft-timeout-banner" role="status" aria-live="polite">
            <div className="lc-soft-timeout-copy">
              <strong>This response is taking longer than expected.</strong>
              <span>It has been running for over 2 minutes. Continue waiting?</span>
            </div>
            <button
              type="button"
              className="lc-soft-timeout-btn"
              onClick={handleContinueLongRun}
            >
              Continue waiting
            </button>
          </div>
        )}

        {pendingPromptSteering && (
          <div className="lc-steering-banner" role="status" aria-live="polite">
            <div className="lc-steering-banner-copy">
              <strong>Continue this task or start a new topic?</strong>
              <span>
                {pendingPromptSteering.unresolvedCount > 0
                  ? `${pendingPromptSteering.unresolvedCount} unresolved objective${pendingPromptSteering.unresolvedCount === 1 ? "" : "s"} detected.`
                  : "The new prompt might be related to the current run."}{" "}
                Auto-starting a new topic in {steeringSeconds}s.
              </span>
            </div>
            <div className="lc-steering-banner-actions">
              <button
                type="button"
                className="lc-steering-btn"
                onClick={() => resolvePromptSteering("continue")}
              >
                Continue task
              </button>
              <button
                type="button"
                className="lc-steering-btn secondary"
                onClick={() => resolvePromptSteering("new_topic")}
              >
                New topic
              </button>
            </div>
          </div>
        )}

        {/* Attachments preview */}
        {attachments.length > 0 && (
          <div style={{ marginBottom: "8px" }} aria-label="Attached files">
            <AttachmentPreviewList
              attachments={attachments}
              onRemove={removeAttachment}
              variant="input"
            />
          </div>
        )}

        {/* Input box */}
        <div
          className={`lc-input-box ${isDragOver ? "drag-over" : ""}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          role="group"
          aria-label="Message input area"
        >
          <div className="lc-web-mode-select-wrap">
            <select
              className="lc-web-mode-select"
              value={webSearchMode}
              onChange={handleWebModeChange}
              aria-label="Web search mode"
              title="Web search mode for this conversation"
            >
              <option value="off">Web Off</option>
              <option value="on">Web On</option>
            </select>
          </div>

          {/* File attachment button */}
          <button
            className="lc-action-btn"
            onClick={openFilePicker}
            aria-label="Attach file (images, PDF, text files supported)"
            type="button"
          >
            <Paperclip size={18} />
          </button>

          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,.png,.jpg,.jpeg,.jfif,.gif,.webp,.bmp,.tif,.tiff,.heic,.heif,.avif,.svg,.ico,.pdf,.txt,.log,.md,.json,.csv,text/plain"
            onChange={handleFileInputChange}
            style={{ display: "none" }}
            aria-hidden="true"
            tabIndex={-1}
          />

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            className="lc-textarea"
            placeholder="Message Agent Sparrow..."
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            wrap="soft"
            rows={1}
            aria-label="Message input"
            aria-describedby="input-footer"
          />

          {/* Send/Stop button */}
          <div className="lc-input-actions">
            {isStreaming && (
              <button
                className="lc-send-btn lc-stop-btn"
                onClick={handleStop}
                aria-label="Stop generating response"
                type="button"
              >
                <Square size={16} />
              </button>
            )}
            <button
              className="lc-send-btn"
              onClick={handleSubmit}
              disabled={!input.trim() && attachments.length === 0}
              aria-label="Send message"
              type="button"
            >
              <ArrowUp size={18} />
            </button>
          </div>
        </div>

        {/* Footer text */}
        <div id="input-footer" className="lc-input-footer">
          <span>
            Agent Sparrow can make mistakes. Please verify important information.
          </span>
          <span
            className={`lc-web-mode-badge ${webSearchMode === "on" ? "on" : "off"}`}
          >
            Next run: Web {webSearchMode === "on" ? "On" : "Off"}
          </span>
        </div>
      </div>
    </div>
  );
}

export default ChatInput;
