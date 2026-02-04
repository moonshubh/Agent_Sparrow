import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import Link from "@tiptap/extension-link";
import { Markdown } from "@tiptap/markdown";
import type { AnyExtension } from "@tiptap/core";

import { ArtifactDirective } from "./artifact-directive";
import { createCodeBlockExtension } from "./code-block";
import { createImageExtension } from "./image";
import { createMathExtension } from "./math";
import { createTableExtensions } from "./table";
import { createTaskListExtensions } from "./task-list";

export interface ExtensionOptions {
  placeholder?: string;
  enableMath?: boolean;
  enableTables?: boolean;
  enableTaskList?: boolean;
  enableImages?: boolean;
}

export const createExtensions = (options: ExtensionOptions = {}) => {
  const extensions: AnyExtension[] = [
    StarterKit.configure({
      codeBlock: false,
    }),
    Markdown.configure({
      markedOptions: {
        gfm: true,
      },
    }),
    Link.configure({
      openOnClick: false,
    }),
    Placeholder.configure({
      placeholder: options.placeholder ?? "Edit message...",
    }),
  ];

  if (options.enableMath !== false) {
    extensions.push(createMathExtension());
  }

  if (options.enableTables !== false) {
    extensions.push(...createTableExtensions());
  }

  if (options.enableTaskList !== false) {
    extensions.push(...createTaskListExtensions());
  }

  if (options.enableImages !== false) {
    extensions.push(createImageExtension());
  }

  extensions.push(createCodeBlockExtension(), ArtifactDirective);

  return extensions;
};
