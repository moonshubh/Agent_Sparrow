"use client";

import Image from "@tiptap/extension-image";
import { ReactNodeViewRenderer } from "@tiptap/react";
import { MemoryImageView } from "./MemoryImageView";
import {
  parseMemoryImageSrc,
  parseDimensionValue,
  withSizeFragment,
} from "@/features/memory/lib/memoryImageSizing";

export const MemoryImageExtension = Image.extend({
  name: "image",
  addNodeView() {
    return ReactNodeViewRenderer(MemoryImageView);
  },
  parseMarkdown: (token, helpers) => {
    const parsed = parseMemoryImageSrc(token.href || "");
    return helpers.createNode("image", {
      src: parsed.baseSrc,
      title: token.title,
      alt: token.text,
      width: parsed.width ?? null,
      height: parsed.height ?? null,
    });
  },
  renderMarkdown: (node) => {
    const src = withSizeFragment(
      node.attrs?.src ?? "",
      parseDimensionValue(node.attrs?.width),
      parseDimensionValue(node.attrs?.height),
    );
    const alt = node.attrs?.alt ?? "";
    const title = node.attrs?.title ?? "";
    return title ? `![${alt}](${src} "${title}")` : `![${alt}](${src})`;
  },
});
