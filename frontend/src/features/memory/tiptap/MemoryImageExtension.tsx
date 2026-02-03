'use client';

import Image from '@tiptap/extension-image';
import { ReactNodeViewRenderer } from '@tiptap/react';
import { MemoryImageView } from './MemoryImageView';

export const MemoryImageExtension = Image.extend({
  name: 'image',
  addNodeView() {
    return ReactNodeViewRenderer(MemoryImageView);
  },
});

