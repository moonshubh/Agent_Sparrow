import type { SerializedArtifact } from '@/features/librechat/AgentContext';
import type { Artifact } from './types';

export const serializeArtifact = (artifact: Artifact): SerializedArtifact => ({
  id: artifact.id,
  type: artifact.type,
  title: artifact.title,
  content: artifact.content,
  language: artifact.language,
  identifier: artifact.identifier,
  index: artifact.index,
  imageUrl: artifact.imageUrl,
  mimeType: artifact.mimeType,
  altText: artifact.altText,
  aspectRatio: artifact.aspectRatio,
  resolution: artifact.resolution,
});
