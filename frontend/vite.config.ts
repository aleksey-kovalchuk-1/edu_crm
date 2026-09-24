/// <reference types="vitest/config" />
import { defineConfig } from "vite";
export default defineConfig({
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // styles.test.ts reads the stylesheet via `?raw`; Vitest stubs unlisted CSS to "".
    css: { include: [/styles\.css/] },
  },
});
