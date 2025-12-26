import { CodeBlockLowlight } from '@tiptap/extension-code-block-lowlight';
import { all, createLowlight } from 'lowlight';

const lowlight = createLowlight(all);

export const createCodeBlockExtension = () =>
  CodeBlockLowlight.configure({
    lowlight,
    HTMLAttributes: { class: 'lc-code-block' },
  });
