import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // Windows Docker Desktop bind mounts don't reliably propagate inotify
    // events into the Linux container, so Vite's default watcher can miss
    // file changes entirely — poll instead so HMR actually fires.
    watch: {
      usePolling: true,
      interval: 300,
    },
  },
});
