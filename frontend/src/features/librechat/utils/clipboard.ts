/**
 * Shared clipboard utilities for LibreChat feature
 *
 * Provides consistent clipboard operations with error handling.
 */

/**
 * Copy text to clipboard with error handling
 *
 * @param text - Text to copy
 * @returns Promise that resolves to true on success, false on failure
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (!navigator.clipboard) {
      console.error("Clipboard API not available");
      return false;
    }
    await navigator.clipboard.writeText(text);
    return true;
  } catch (error) {
    console.error("Failed to copy text:", error);
    return false;
  }
}

/**
 * Copy text to clipboard with a callback for success feedback
 *
 * @param text - Text to copy
 * @param onSuccess - Optional callback called on successful copy
 * @returns Promise that resolves to true on success, false on failure
 */
export async function copyToClipboardWithCallback(
  text: string,
  onSuccess?: () => void,
): Promise<boolean> {
  const success = await copyToClipboard(text);
  if (success && onSuccess) {
    onSuccess();
  }
  return success;
}
