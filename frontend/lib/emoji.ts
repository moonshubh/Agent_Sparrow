/**
 * Section emoji icons for executive summary sign-posting
 * Used to help users quickly identify and scan through key sections
 */
export const sectionIcon = {
  summary: "📝",
  issues: "🚩", 
  fixes: "💡",
} as const;

/**
 * Maps common section heading patterns to their appropriate emoji icons
 * Used by the markdown preprocessor to automatically inject emojis
 */
export const sectionPatterns = [
  { pattern: /^(executive\s+summary|summary)$/i, emoji: sectionIcon.summary },
  { pattern: /^(key\s+issues?\s+identified?|issues?\s+found|identified\s+issues?|problems?\s+detected|issues?)$/i, emoji: sectionIcon.issues },
  { pattern: /^(recommended\s+solutions?|solutions?|solution|fixes?|recommendations?)$/i, emoji: sectionIcon.fixes },
] as const;

/**
 * Wraps emoji in proper accessibility markup for screen readers
 * @param emoji - The emoji character to wrap
 * @param label - Accessible label for screen readers
 * @returns JSX span element with proper ARIA attributes
 */
export function accessibleEmoji(emoji: string, label: string): string {
  return `<span role="img" aria-label="${label}">${emoji}</span>`;
}

/**
 * Non-breaking space character for proper emoji spacing
 */
export const NBSP = '\u00A0';