import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/* La app vive en la raíz. El basename del router sale de aquí
   (import.meta.env.BASE_URL, ver src/rutas.js). */
const BASE = "/";
const SERVIDOR = "http://localhost:8000";

/* En desarrollo, /msal/silencioso (sin .html, como la sirve FastAPI) es la
   página vacía de public/msal/silencioso.html, no la app. */
const paginaSilenciosa = {
  name: "pagina-silenciosa",
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (/^\/msal\/silencioso(\?|#|$)/.test(req.url || "")) req.url = req.url.replace("/msal/silencioso", "/msal/silencioso.html");
      next();
    });
  },
};

export default defineConfig({
  base: BASE,
  plugins: [react(), paginaSilenciosa],
  server: {
    /* npm run dev: la API la sirve FastAPI. */
    proxy: { "/api": SERVIDOR, "/health": SERVIDOR },
  },
  build: { outDir: "dist", emptyOutDir: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/pruebas/setup.js"],
    css: false,
    /* jsdom con userEvent es lento en esta máquina: las pruebas largas del
       detalle pasan de los 5 s por defecto. */
    testTimeout: 20000,
  },
});
