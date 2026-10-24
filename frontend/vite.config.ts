import basicSsl from "@vitejs/plugin-basic-ssl";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const BACKEND = "http://localhost:8000";

// `npm run dev` serves http://localhost:5173 for laptop use.
// `npm run dev:phone` serves HTTPS on the local network. Browsers only expose the
// microphone on secure origins (HTTPS or localhost), so a phone opening
// http://<laptop-ip>:5173 could never record. The certificate is self-signed: accept
// the warning once on the phone.
export default defineConfig(({ mode }) => {
  const phone = mode === "phone";
  return {
    plugins: [react(), ...(phone ? [basicSsl()] : [])],
    server: {
      host: phone ? true : "localhost",
      port: 5173,
      proxy: {
        // REST. Page routes (/ and /dashboard) are NOT proxied.
        "/reports": { target: BACKEND, changeOrigin: true },
        "/queues": { target: BACKEND, changeOrigin: true },
        "/scenarios": { target: BACKEND, changeOrigin: true },
        "/health": { target: BACKEND, changeOrigin: true },
        // All WebSockets live under /ws on the backend.
        "/ws": { target: BACKEND, ws: true, changeOrigin: true },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      include: ["tests/**/*.test.{ts,tsx}"],
    },
  };
});
