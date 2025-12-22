/**
 * Artifact Detection Plugin for Remark
 * 
 * A remark plugin that detects artifact directives and code blocks
 * that should be treated as artifacts, and transforms them into
 * artifact nodes for rendering.
 * 
 * Detection strategies:
 * 1. Explicit ::artifact{} directives
 * 2. ```mermaid code blocks (auto-artifact)
 * 3. ```html/jsx/tsx blocks with `// artifact` marker
 */

import { visit } from 'unist-util-visit';
import type { Plugin } from 'unified';
import type { Root, Code, Parent } from 'mdast';
import { ARTIFACT_DEFAULTS, isArtifactLanguage } from './types';
import type { ArtifactType, ArtifactDirectiveProps } from './types';

// Extended node type for directive nodes from remark-directive
interface DirectiveNode {
  type: 'textDirective' | 'leafDirective' | 'containerDirective';
  name: string;
  attributes?: Record<string, string>;
  children?: any[];
  data?: {
    hName?: string;
    hProperties?: Record<string, any>;
  };
}

// Extended code node with artifact metadata
interface ArtifactCodeNode extends Code {
  data?: {
    hName?: string;
    hProperties?: {
      isArtifact?: boolean;
      artifactType?: ArtifactType;
      artifactTitle?: string;
      artifactIdentifier?: string;
      artifactLanguage?: string;
    };
  };
}

/**
 * Check if a code block should be auto-detected as an artifact
 */
function shouldAutoDetectAsArtifact(node: Code): {
  isArtifact: boolean;
  type?: ArtifactType;
  title?: string;
} {
  const lang = (node.lang || '').toLowerCase();
  const content = node.value || '';
  const firstLine = content.split('\n')[0] || '';

  // Mermaid blocks are always artifacts
  if (lang === 'mermaid') {
    return {
      isArtifact: true,
      type: 'mermaid',
      title: 'Mermaid Diagram',
    };
  }

  // Check for explicit artifact marker in first line
  // Pattern: // artifact or /* artifact */ or # artifact
  const artifactMarkerPattern = /^(?:\/\/|\/\*|#)\s*artifact(?:\s*\*\/)?/i;
  if (artifactMarkerPattern.test(firstLine.trim())) {
    // Determine type based on language
    let type: ArtifactType = 'code';
    if (lang === 'html') type = 'html';
    else if (lang === 'jsx' || lang === 'tsx') type = 'react';

    // Try to extract title from marker: // artifact: My Title
    const titleMatch = firstLine.match(/artifact[:\s]+(.+?)(?:\*\/)?$/i);
    const title = titleMatch ? titleMatch[1].trim() : `${lang.toUpperCase()} Artifact`;

    return {
      isArtifact: true,
      type,
      title,
    };
  }

  return { isArtifact: false };
}

/**
 * Remark plugin to detect and transform artifact directives and code blocks
 */
export const artifactPlugin: Plugin<[], Root> = () => {
  return (tree: Root) => {
    // First pass: Handle directive nodes (::artifact{})
    visit(
      tree,
      ['textDirective', 'leafDirective', 'containerDirective'],
      (node: any, index, parent) => {
        // Handle text directives that aren't artifact - preserve them as text
        if (node.type === 'textDirective' && node.name !== 'artifact') {
          const replacementText = `:${node.name}`;
          if (parent && Array.isArray(parent.children) && typeof index === 'number') {
            parent.children[index] = {
              type: 'text',
              value: replacementText,
            };
          }
          return;
        }

        // Only process artifact directives
        if (node.name !== 'artifact') {
          return;
        }

        const attrs = (node.attributes || {}) as ArtifactDirectiveProps;

        // Transform directive to custom artifact node
        node.data = {
          hName: 'artifact',
          hProperties: {
            type: attrs.type || ARTIFACT_DEFAULTS.type,
            title: attrs.title || ARTIFACT_DEFAULTS.title,
            identifier: attrs.identifier || ARTIFACT_DEFAULTS.identifier,
            language: attrs.language,
          },
          ...node.data,
        };

        return node;
      }
    );

    // Second pass: Handle code blocks that should be artifacts
    visit(tree, 'code', (node: Code, index, parent: Parent | undefined) => {
      const detection = shouldAutoDetectAsArtifact(node);

      if (detection.isArtifact) {
        // Transform code block to include artifact metadata
        const artifactNode = node as ArtifactCodeNode;
        artifactNode.data = {
          ...artifactNode.data,
          hProperties: {
            ...artifactNode.data?.hProperties,
            isArtifact: true,
            artifactType: detection.type,
            artifactTitle: detection.title,
            artifactLanguage: node.lang || undefined,
          },
        };
      }
    });
  };
};

/**
 * Extract text content from React children (for artifact content extraction)
 */
export function extractContent(children: React.ReactNode): string {
  if (typeof children === 'string') {
    return children;
  }

  if (Array.isArray(children)) {
    return children.map(extractContent).join('');
  }

  if (children && typeof children === 'object' && 'props' in children) {
    const props = children.props as { children?: React.ReactNode };
    if (props.children) {
      return extractContent(props.children);
    }
  }

  return '';
}

/**
 * Parse artifact attributes from directive string
 * Example: ::artifact{type="mermaid" title="System Diagram"}
 */
export function parseArtifactAttributes(attrString: string): ArtifactDirectiveProps {
  const attrs: ArtifactDirectiveProps = {};
  
  // Match key="value" patterns
  const attrPattern = /(\w+)="([^"]+)"/g;
  let match;
  
  while ((match = attrPattern.exec(attrString)) !== null) {
    const [, key, value] = match;
    if (key === 'type') attrs.type = value;
    else if (key === 'title') attrs.title = value;
    else if (key === 'identifier') attrs.identifier = value;
    else if (key === 'language') attrs.language = value;
  }
  
  return attrs;
}

export default artifactPlugin;
