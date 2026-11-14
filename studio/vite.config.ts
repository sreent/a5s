// The studio, built into the channels app's pages (src/a5s/core/webchat/studio), which serves
// it under /studio/ with the same policy as every page: a5s's own scripts and styles alone.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "/studio/",
  build: {
    outDir: "../src/a5s/core/webchat/studio",
    emptyOutDir: true,
    sourcemap: false,
    modulePreload: { polyfill: false },  // nothing inline: the policy runs no inline script
  },
  server: { fs: { allow: [".."] } },  // the pages' shared stylesheet, beside the studio
});
