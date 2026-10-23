import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The browser only talks to the Vite server. Anything starting with /api is
// forwarded to the FastAPI backend, so there are no CORS problems and only ONE
// public URL is needed (important on Replit).
const backendUrl = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

const serverSettings = {
  host: "0.0.0.0",
  port: 5173,
  allowedHosts: true, // Replit serves the app from a changing *.replit.dev host name
  proxy: {
    "/api": { target: backendUrl, changeOrigin: true },
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: serverSettings,
  preview: { ...serverSettings, port: 4173 },
});
