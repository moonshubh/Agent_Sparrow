import Image from "@tiptap/extension-image";
import { mergeAttributes } from "@tiptap/core";
import { getGlobalArtifactStore } from "@/features/librechat/artifacts/ArtifactContext";
import {
  resolveArtifactImageByRef,
  resolveImageSrc,
} from "@/features/librechat/artifacts/imageUtils";

const resolveArtifactSrc = (src: string, alt?: string): string | null => {
  const store = getGlobalArtifactStore();
  if (!store) return null;

  const artifactsById = store.getState().artifactsById;
  const ref = src.replace(/^artifact:/, "").trim();
  if (!ref) return null;

  const artifact = resolveArtifactImageByRef(artifactsById, ref, alt);
  return artifact ? resolveImageSrc(artifact) : null;
};

export const ArtifactImage = Image.extend({
  name: "image",

  renderHTML({ HTMLAttributes }) {
    const src =
      typeof HTMLAttributes.src === "string" ? HTMLAttributes.src : "";
    const alt =
      typeof HTMLAttributes.alt === "string" ? HTMLAttributes.alt : "";
    const resolvedSrc = src.startsWith("artifact:")
      ? resolveArtifactSrc(src, alt) || src
      : src;

    return ["img", mergeAttributes(HTMLAttributes, { src: resolvedSrc })];
  },
});

export default ArtifactImage;
