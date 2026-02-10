import type { JSONContent } from "@tiptap/core";
import {
  parseDimensionValue,
  parseMemoryImageSrc,
  withSizeFragment,
} from "@/features/memory/lib/memoryImageSizing";

type ImageSize = {
  baseSrc: string;
  width: number;
  height: number;
};

const MARKDOWN_IMAGE_REGEX = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g;

const collectImageSizesFromDoc = (
  node: JSONContent | null | undefined,
  output: ImageSize[],
): void => {
  if (!node) return;

  if (node.type === "image") {
    const attrs = (node.attrs ?? {}) as Record<string, unknown>;
    const src = typeof attrs.src === "string" ? attrs.src : "";
    const width = parseDimensionValue(attrs.width);
    const height = parseDimensionValue(attrs.height);
    if (src && width && height) {
      output.push({
        baseSrc: parseMemoryImageSrc(src).baseSrc,
        width,
        height,
      });
    }
  }

  const children = Array.isArray(node.content) ? node.content : [];
  children.forEach((child) => collectImageSizesFromDoc(child, output));
};

const buildQueueByBaseSrc = (sizes: ImageSize[]): Map<string, ImageSize[]> => {
  const queueByBaseSrc = new Map<string, ImageSize[]>();
  sizes.forEach((size) => {
    const existing = queueByBaseSrc.get(size.baseSrc);
    if (existing) {
      existing.push(size);
      return;
    }
    queueByBaseSrc.set(size.baseSrc, [size]);
  });
  return queueByBaseSrc;
};

const applyImageSizesToMarkdown = (
  markdown: string,
  queueByBaseSrc: Map<string, ImageSize[]>,
): string => {
  if (!markdown) return markdown;

  return markdown.replace(
    MARKDOWN_IMAGE_REGEX,
    (match, altRaw: string, srcRaw: string, titleRaw: string | undefined) => {
      const alt = altRaw ?? "";
      const title = titleRaw ?? "";
      const currentBaseSrc = parseMemoryImageSrc(srcRaw).baseSrc;
      const sizeQueue = queueByBaseSrc.get(currentBaseSrc);
      const nextSize = sizeQueue?.shift();
      if (!nextSize) return match;

      const sizedSrc = withSizeFragment(
        currentBaseSrc,
        nextSize.width,
        nextSize.height,
      );
      return title
        ? `![${alt}](${sizedSrc} "${title}")`
        : `![${alt}](${sizedSrc})`;
    },
  );
};

const collectSizedImagesFromMarkdown = (markdown: string): ImageSize[] => {
  const collected: ImageSize[] = [];
  markdown.replace(
    MARKDOWN_IMAGE_REGEX,
    (_match, _altRaw: string, srcRaw: string) => {
      const parsed = parseMemoryImageSrc(srcRaw);
      if (parsed.baseSrc && parsed.width && parsed.height) {
        collected.push({
          baseSrc: parsed.baseSrc,
          width: parsed.width,
          height: parsed.height,
        });
      }
      return "";
    },
  );
  return collected;
};

export const normalizeMarkdownImageSizing = (
  markdown: string,
  options?: {
    editorDoc?: JSONContent | null;
    fallbackMarkdown?: string;
  },
): string => {
  if (!markdown) return markdown;

  const imageSizes: ImageSize[] = [];
  collectImageSizesFromDoc(options?.editorDoc ?? null, imageSizes);

  if (imageSizes.length === 0 && options?.fallbackMarkdown) {
    imageSizes.push(...collectSizedImagesFromMarkdown(options.fallbackMarkdown));
  }

  if (imageSizes.length === 0) return markdown;

  return applyImageSizesToMarkdown(markdown, buildQueueByBaseSrc(imageSizes));
};

