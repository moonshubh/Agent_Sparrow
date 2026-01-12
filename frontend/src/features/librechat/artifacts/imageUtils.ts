import type { Artifact } from './types';

export function normalizeImageRef(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

export function resolveImageSrc(artifact: Artifact): string | null {
  if (artifact.imageUrl) {
    return artifact.imageUrl;
  }

  if (artifact.imageData) {
    const mimeType = artifact.mimeType || 'image/png';
    return `data:${mimeType};base64,${artifact.imageData}`;
  }

  if (artifact.content) {
    const trimmed = artifact.content.trim();
    if (/^(https?:|data:|blob:)/i.test(trimmed)) {
      return trimmed;
    }
  }

  return null;
}

export function findImageByTitle(
  artifactsById: Record<string, Artifact>,
  title: string
): Artifact | undefined {
  const normalizedTitle = normalizeImageRef(title);
  if (!normalizedTitle) return undefined;

  const imageArtifacts = Object.values(artifactsById).filter((a) => a.type === 'image');

  const exactMatch = imageArtifacts.find(
    (a) => normalizeImageRef(a.title || '') === normalizedTitle
  );
  if (exactMatch) return exactMatch;

  const partialMatch = imageArtifacts.find((a) => {
    const normalizedCandidate = normalizeImageRef(a.title || '');
    return normalizedCandidate.includes(normalizedTitle) || normalizedTitle.includes(normalizedCandidate);
  });
  if (partialMatch) return partialMatch;

  return imageArtifacts.find(
    (a) => (a.title || '').toLowerCase().includes(title.toLowerCase())
  );
}

export function resolveArtifactImageByRef(
  artifactsById: Record<string, Artifact>,
  ref: string,
  altText?: string
): Artifact | undefined {
  const normalizedRef = String(ref || '').trim();
  if (!normalizedRef) {
    return altText ? findImageByTitle(artifactsById, altText) : undefined;
  }

  const directMatch = artifactsById[normalizedRef];
  if (directMatch?.type === 'image') {
    return directMatch;
  }

  const refLower = normalizedRef.toLowerCase();
  const exactIdMatch = Object.values(artifactsById).find(
    (artifact) => artifact.type === 'image' && artifact.id.toLowerCase() === refLower
  );
  if (exactIdMatch) return exactIdMatch;

  const partialIdMatch = Object.values(artifactsById).find(
    (artifact) => artifact.type === 'image' && artifact.id.toLowerCase().includes(refLower)
  );
  if (partialIdMatch) return partialIdMatch;

  if (altText) {
    const titleMatch = findImageByTitle(artifactsById, altText);
    if (titleMatch) return titleMatch;
  }

  return findImageByTitle(artifactsById, normalizedRef);
}
