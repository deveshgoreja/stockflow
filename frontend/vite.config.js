import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Read VITE_API_URL from the repository-level .env shared with the backend.
  envDir: "..",
  server: { host: true, port: 5173 },
});
