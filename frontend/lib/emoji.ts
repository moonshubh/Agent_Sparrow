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
 * A simple utility to escape HTML characters in a string.
 * This prevents XSS when inserting dynamic data into HTML.
 * @param unsafe The string to escape.
 * @returns The escaped string.
 */
function escapeHtml(unsafe: string): string {
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
}

/**
 * Wraps emoji in proper accessibility markup for screen readers.
 * This function returns an HTML string, which must be rendered using `dangerouslySetInnerHTML`.
 * @param emoji - The emoji character to wrap
 * @param label - Accessible label for screen readers. This will be safely escaped.
 * @returns An HTML string with proper ARIA attributes for the emoji.
 */
export function accessibleEmoji(emoji: string, label: string): string {
  const safeLabel = escapeHtml(label);
  return `<span role="img" aria-label="${safeLabel}">${emoji}</span>`;
}

/**
 * Non-breaking space character for proper emoji spacing
 */
export const NBSP = '\u00A0';