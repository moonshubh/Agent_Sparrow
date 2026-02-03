import type { AnyExtension } from '@tiptap/core';
import { createExtensions, type ExtensionOptions } from '@/features/librechat/components/tiptap/extensions';
import { MemoryImageExtension } from './MemoryImageExtension';
import Underline from '@tiptap/extension-underline';

export const createMemoryExtensions = (options: ExtensionOptions = {}) => {
  const extensions = createExtensions({
    ...options,
    enableImages: false,
  }) as AnyExtension[];

  extensions.push(MemoryImageExtension);
  extensions.push(Underline);

  return extensions;
};
