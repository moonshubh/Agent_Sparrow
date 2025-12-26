import { ArtifactImage } from './artifact-image';

export const createImageExtension = () =>
  ArtifactImage.configure({
    allowBase64: false,
  });
