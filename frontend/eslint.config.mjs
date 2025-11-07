import path from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
  resolvePluginsRelativeTo: __dirname,
});

const typescriptRuleOverrides = {
  files: ["**/*.ts", "**/*.tsx"],
  ignores: [
    "src/features/global-knowledge/**/*",
    "src/app/chat/components/Attachments.tsx",
    "src/services/api/api-client.ts",
  ],
  rules: {
    "@typescript-eslint/no-unused-vars": "off",
    "@typescript-eslint/no-explicit-any": "off",
    "@typescript-eslint/no-empty-object-type": "off",
    "react/no-unescaped-entities": "off",
    "@next/next/no-img-element": "off",
  },
};

export default [
  ...compat.config({
    extends: ["next/core-web-vitals", "next/typescript"],
  }),
  typescriptRuleOverrides,
];
