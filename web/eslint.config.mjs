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
    // Vendored upstream source — see `web/vendor/thinking-orbs/index.ts` for
    // provenance and the list of local changes.
    //
    // Both hooks it ships seed their state from `matchMedia` with a
    // synchronous `setState` in the effect body, which the React Compiler rule
    // rejects. Rewriting them would deepen every future re-sync in exchange
    // for one render at mount, so the rule is off here rather than the file
    // being skipped: everything else still gets linted.
    files: ["vendor/**/*.{ts,tsx}"],
    rules: {
      "react-hooks/set-state-in-effect": "off",
    },
  },
  {
    // ``.next-*`` covers every build output, including the throwaway dist dirs
    // a second dev server needs (DEEPTUTOR_NEXT_DIST_DIR, see next.config.js):
    // without it, running one turns `npx eslint .` — a CI gate — red with
    // hundreds of errors from generated code.
    ignores: [
      "node_modules/**",
      ".next/**",
      ".next-*/**",
      "dist/**",
      "out/**",
      "tmp/**",
      "coverage/**",
      "playwright-report/**",
      "test-results/**",
      "contracts/generated/.tmp/**",
    ],
  },
];

export default config;
