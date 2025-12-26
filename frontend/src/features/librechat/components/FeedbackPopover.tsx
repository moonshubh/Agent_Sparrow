'use client';

import React, { useState, useCallback, memo, useEffect, useRef } from 'react';
import { ThumbsUp, ThumbsDown, ChevronDown, Check } from 'lucide-react';
import * as Popover from '@radix-ui/react-popover';

const POSITIVE_CATEGORIES = [
  { id: 'accurate', label: 'Accurate & Reliable' },
  { id: 'creative', label: 'Creative Solution' },
  { id: 'clear', label: 'Clear & Well-Written' },
] as const;

const NEGATIVE_CATEGORIES = [
  { id: 'inaccurate', label: 'Inaccurate Information' },
  { id: 'not_helpful', label: 'Not Helpful' },
  { id: 'bad_style', label: 'Poor Writing Style' },
  { id: 'off_topic', label: 'Off Topic' },
  { id: 'other', label: 'Other Issue' },
] as const;

type FeedbackType = 'positive' | 'negative';
type PositiveCategory = typeof POSITIVE_CATEGORIES[number]['id'];
type NegativeCategory = typeof NEGATIVE_CATEGORIES[number]['id'];

interface FeedbackPopoverProps {
  messageId: string;
  sessionId?: string;
  onSubmit?: (type: FeedbackType, category: string) => Promise<void>;
}

export const FeedbackPopover = memo(function FeedbackPopover({
  messageId,
  sessionId,
  onSubmit,
}: FeedbackPopoverProps) {
  const [feedbackType, setFeedbackType] = useState<FeedbackType | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup timeouts on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) {
        clearTimeout(closeTimeoutRef.current);
      }
    };
  }, []);

  const handleFeedbackClick = useCallback((type: FeedbackType) => {
    if (submitted) return;
    setFeedbackType(type);
    setSelectedCategory(null);
  }, [submitted]);

  const handleCategorySelect = useCallback(async (category: string) => {
    if (!feedbackType || isSubmitting) return;

    setSelectedCategory(category);
    setIsSubmitting(true);

    try {
      if (onSubmit) {
        await onSubmit(feedbackType, category);
      } else {
        // Default submission to API
        await submitFeedback(messageId, sessionId, feedbackType, category);
      }
      setSubmitted(true);
      // Close popover after short delay (with cleanup ref to prevent memory leak)
      closeTimeoutRef.current = setTimeout(() => setIsOpen(false), 800);
    } catch (error) {
      console.error('[FeedbackPopover] Failed to submit feedback:', error);
    } finally {
      setIsSubmitting(false);
    }
  }, [feedbackType, isSubmitting, messageId, sessionId, onSubmit]);

  const categories = feedbackType === 'positive' ? POSITIVE_CATEGORIES : NEGATIVE_CATEGORIES;

  return (
    <Popover.Root open={isOpen} onOpenChange={setIsOpen}>
      <div className="lc-feedback-buttons">
        {/* Thumbs Up */}
        <Popover.Trigger asChild>
          <button
            className={`lc-action-btn ${feedbackType === 'positive' && submitted ? 'lc-feedback-submitted' : ''}`}
            onClick={() => handleFeedbackClick('positive')}
            aria-label="Good response"
            disabled={submitted}
          >
            <ThumbsUp
              size={14}
              className={feedbackType === 'positive' && submitted ? 'lc-feedback-positive' : ''}
            />
          </button>
        </Popover.Trigger>

        {/* Thumbs Down */}
        <Popover.Trigger asChild>
          <button
            className={`lc-action-btn ${feedbackType === 'negative' && submitted ? 'lc-feedback-submitted' : ''}`}
            onClick={() => handleFeedbackClick('negative')}
            aria-label="Bad response"
            disabled={submitted}
          >
            <ThumbsDown
              size={14}
              className={feedbackType === 'negative' && submitted ? 'lc-feedback-negative' : ''}
            />
          </button>
        </Popover.Trigger>
      </div>

      <Popover.Portal>
        <Popover.Content
          className="lc-feedback-popover"
          side="top"
          sideOffset={8}
          align="start"
        >
          {submitted ? (
            <div className="lc-feedback-success">
              <Check size={16} className="lc-feedback-check" />
              <span>Thanks for your feedback!</span>
            </div>
          ) : feedbackType ? (
            <div className="lc-feedback-categories">
              <p className="lc-feedback-prompt">
                {feedbackType === 'positive'
                  ? 'What did you like about this response?'
                  : 'What was the issue with this response?'}
              </p>
              <div className="lc-feedback-category-list">
                {categories.map((cat) => (
                  <button
                    key={cat.id}
                    className={`lc-feedback-category ${selectedCategory === cat.id ? 'selected' : ''}`}
                    onClick={() => handleCategorySelect(cat.id)}
                    disabled={isSubmitting}
                  >
                    {cat.label}
                    {selectedCategory === cat.id && isSubmitting && (
                      <span className="lc-feedback-spinner" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="lc-feedback-instructions">
              <p>Click thumbs up or down to provide feedback</p>
            </div>
          )}
          <Popover.Arrow className="lc-feedback-arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
});

// API helper function
async function submitFeedback(
  messageId: string,
  sessionId: string | undefined,
  feedbackType: FeedbackType,
  category: string
): Promise<void> {
  const response = await fetch('/api/v1/feedback/message', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message_id: messageId,
      session_id: sessionId,
      feedback_type: feedbackType,
      category,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to submit feedback: ${response.statusText}`);
  }
}

export default FeedbackPopover;
