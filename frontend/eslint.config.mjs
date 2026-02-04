import coreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const typescriptRuleOverrides = {
  files: ["**/*.ts", "**/*.tsx"],
  ignores: [
    "src/features/global-knowledge/**/*",
    "src/app/chat/components/Attachments.tsx",
  ],
  rules: {
    "@typescript-eslint/no-unused-vars": "off",
    "@typescript-eslint/no-explicit-any": "off",
    "@typescript-eslint/no-empty-object-type": "off",
    "react/no-unescaped-entities": "off",
    "@next/next/no-img-element": "off",
  },
};

const nodeScriptOverrides = {
  files: ["next.config.js", "scripts/**/*.js"],
  rules: {
    "@typescript-eslint/no-require-imports": "off",
  },
};

const config = [
  ...coreWebVitals,
  ...nextTypescript,
  typescriptRuleOverrides,
  nodeScriptOverrides,
];

export default config;
