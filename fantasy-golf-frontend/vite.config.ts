import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// When running inside Docker, process.env.VITE_API_TARGET resolves to the
// backend service name (http://backend:8000). Natively, it falls back to
// localhost so the dev workflow is unchanged.
const apiTarget = process.env.VITE_API_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",  // required so Vite is reachable from outside the container
    // Proxy /api calls to the FastAPI backend during local development.
    // This avoids CORS issues when the frontend and backend run on different ports.
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
