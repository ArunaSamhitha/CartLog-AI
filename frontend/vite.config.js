import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api calls go to the FastAPI backend on port 8000.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
});
