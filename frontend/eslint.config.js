import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores(["dist", "node_modules"]),
  {
    files: ["**/*.{ts,tsx,js}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
  },
  {
    files: ["scripts/**/*.mjs"],
    extends: [js.configs.recommended],
    // Node scripts; functions passed to page.evaluate() run in the browser, so both global sets apply.
    languageOptions: { ecmaVersion: 2024, sourceType: "module", globals: { ...globals.node, ...globals.browser } },
  },
]);
