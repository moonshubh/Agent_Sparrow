import { Mathematics } from "@tiptap/extension-mathematics";

export const createMathExtension = () =>
  Mathematics.configure({
    katexOptions: {
      throwOnError: false,
    },
  });
