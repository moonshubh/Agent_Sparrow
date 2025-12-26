/**
 * Artifact System Exports
 * 
 * Centralized exports for the artifact infrastructure.
 */

// Types
export type {
  Artifact,
  ArtifactType,
  ArtifactState,
  ArtifactActions,
  ArtifactStore,
  ArtifactDirectiveProps,
  CodeBlockInfo,
} from './types';

export {
  generateArtifactId,
  isArtifactLanguage,
  ARTIFACT_DEFAULTS,
  ARTIFACT_LANGUAGES,
} from './types';

// Context & Store
export {
  ArtifactProvider,
  useArtifactStore,
  useArtifactSelector,
  useCurrentArtifact,
  useArtifactsVisible,
  useArtifactActions,
  getGlobalArtifactStore,
} from './ArtifactContext';

// Plugin
export { artifactPlugin, extractContent, parseArtifactAttributes } from './artifactPlugin';

// Components
export { ArtifactBadgeOrButton } from './ArtifactBadgeOrButton';
export { ArtifactPanel } from './ArtifactPanel';
export { MermaidEditor } from './MermaidEditor';
export { ArticleEditor } from './ArticleEditor';
