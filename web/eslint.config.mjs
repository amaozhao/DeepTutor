import nextConfig from "eslint-config-next";
import i18nPlugin from "./eslint/i18n-plugin.mjs";

const config = [
  ...nextConfig,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      i18n: i18nPlugin,
    },
    rules: {
      // I18n migration is tracked separately; do not emit noisy warnings in lint.
      "i18n/no-literal-ui-text": "off",
      // Markdown/user-generated media renderers intentionally use raw <img>.
      "@next/next/no-img-element": "off",
      // React Hooks 7 enables React Compiler-oriented rules that currently flag
      // existing app patterns repo-wide. Keep the classic hook safety rules, but
      // avoid turning a dependency bump into a large component rewrite.
      "react-hooks/immutability": "off",
      "react-hooks/preserve-manual-memoization": "off",
      "react-hooks/purity": "off",
      "react-hooks/refs": "off",
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/static-components": "off",
    },
  },
  {
    ignores: ["node_modules/**", ".next/**", "out/**"],
  },
];

export default config;
