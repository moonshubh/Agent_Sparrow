// Type declarations for remark-directive (no official @types package)
declare module 'remark-directive' {
  import type { Plugin } from 'unified';

  /**
   * Remark plugin to support directives (::directive{attrs} syntax).
   * @see https://github.com/remarkjs/remark-directive
   */
  const remarkDirective: Plugin;
  export default remarkDirective;
}
