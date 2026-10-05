import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Development: `npm run dev` serves the React app on :5173 and forwards /api to FastAPI on :8000,
// so the browser sees ONE address (cookies and Google sign-in work normally).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } },
  },
});
