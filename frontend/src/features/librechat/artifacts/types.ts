/**
 * Artifact Types & Interfaces for Agent Sparrow
 * 
 * Defines the core type system for the artifact infrastructure.
 * Artifacts are structured code/diagram outputs that can be viewed
 * in a dedicated panel with preview capabilities.
 */

/**
 * Supported artifact types
 * - react: React/JSX component code
 * - html: HTML markup
 * - mermaid: Mermaid diagram definitions
 * - code: Generic code with syntax highlighting
 * - image: Generated images (base64 encoded)
 * - kb-article: Knowledge base article draft
 * - article: Rich article with images (editable)
 */
export type ArtifactType = 'react' | 'html' | 'mermaid' | 'code' | 'image' | 'kb-article' | 'article';

/**
 * Core artifact interface
 */
export interface Artifact {
  /** Unique identifier for the artifact */
  id: string;
  /** Type of artifact content */
  type: ArtifactType;
  /** Display title for the artifact */
  title: string;
  /** The actual content/code of the artifact */
  content: string;
  /** ID of the message that contains this artifact */
  messageId: string;
  /** Programming language (for code artifacts) */
  language?: string;
  /** Optional identifier from the directive */
  identifier?: string;
  /** Index for ordering multiple artifacts */
  index?: number;
  /** Timestamp of last update */
  lastUpdateTime?: number;

  // Image artifact specific fields
  /** Base64-encoded image data (for image artifacts) */
  imageData?: string;
  /** MIME type of the image (e.g., 'image/png', 'image/jpeg') */
  mimeType?: string;
  /** Alt text for accessibility */
  altText?: string;
  /** Aspect ratio of the generated image */
  aspectRatio?: string;
  /** Resolution of the generated image */
  resolution?: string;
}

/**
 * Artifact state for the store
 */
export interface ArtifactState {
  /** Map of artifact ID to artifact object */
  artifactsById: Record<string, Artifact>;
  /** Currently selected artifact ID */
  currentArtifactId: string | null;
  /** Whether the artifacts panel is visible */
  isArtifactsVisible: boolean;
  /** Ordered list of artifact IDs (for navigation) */
  orderedIds: string[];
}

/**
 * Artifact store actions
 */
export interface ArtifactActions {
  /** Add or update an artifact */
  addArtifact: (artifact: Artifact) => void;
  /** Set the currently viewed artifact */
  setCurrentArtifact: (id: string | null) => void;
  /** Toggle or set artifacts panel visibility */
  setArtifactsVisible: (visible: boolean) => void;
  /** Reset all artifacts (for new session) */
  resetArtifacts: () => void;
  /** Remove a specific artifact */
  removeArtifact: (id: string) => void;
  /** Get artifact by ID */
  getArtifact: (id: string) => Artifact | undefined;
  /** Get all artifacts for a specific message */
  getArtifactsByMessage: (messageId: string) => Artifact[];
}

/**
 * Combined artifact store type
 */
export type ArtifactStore = ArtifactState & ArtifactActions;

/**
 * Props for artifact directive parsing
 */
export interface ArtifactDirectiveProps {
  type?: string;
  title?: string;
  identifier?: string;
  language?: string;
}

/**
 * Code block info for artifact detection
 */
export interface CodeBlockInfo {
  language: string;
  content: string;
  isArtifact: boolean;
  artifactMarker?: string;
}

/**
 * Helper to generate artifact ID
 */
export function generateArtifactId(
  identifier: string,
  type: string,
  title: string,
  messageId: string,
  index?: number
): string {
  const suffix = typeof index === 'number' ? `_idx${index}` : '';
  return `${identifier}_${type}_${title}_${messageId}${suffix}`
    .replace(/\s+/g, '_')
    .toLowerCase();
}

/**
 * Default values for artifacts
 */
export const ARTIFACT_DEFAULTS = {
  title: 'Untitled',
  type: 'code' as ArtifactType,
  identifier: 'artifact',
} as const;

/**
 * Languages that can be auto-detected as artifacts
 */
export const ARTIFACT_LANGUAGES = ['mermaid', 'jsx', 'tsx', 'html'] as const;

/**
 * Check if a language is an artifact-capable language
 */
export function isArtifactLanguage(language: string): boolean {
  return ARTIFACT_LANGUAGES.includes(language.toLowerCase() as any);
}
