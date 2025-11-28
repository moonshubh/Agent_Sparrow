// Type declarations for rehype-highlight (no official @types package)
declare module 'rehype-highlight' {
  import type { Plugin } from 'unified';

  interface Options {
    /**
     * Whether to detect the programming language automatically.
     * @default false
     */
    detect?: boolean;
    /**
     * Whether to ignore missing languages.
     * @default false
     */
    ignoreMissing?: boolean;
    /**
     * Alias languages to other languages.
     */
    aliases?: Record<string, string | string[]>;
    /**
     * List of languages to load.
     */
    languages?: Record<string, unknown>;
    /**
     * List of languages not to highlight.
     */
    plainText?: string[];
    /**
     * Prefix to use for class names.
     * @default 'hljs-'
     */
    prefix?: string;
    /**
     * Subset of languages to detect automatically.
     */
    subset?: string[] | false;
  }

  /**
   * Rehype plugin to highlight code blocks with highlight.js.
   * @see https://github.com/rehypejs/rehype-highlight
   */
  const rehypeHighlight: Plugin<[Options?]>;
  export default rehypeHighlight;
}
