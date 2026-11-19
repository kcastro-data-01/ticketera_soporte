import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/* La app React vive bajo /react/ mientras dura la migración (FastAPI
   devuelve index.html para cualquier /react/*). En la etapa final pasa a la
   raíz: cambiar BASE a "/" (y el basename del router sale de aquí). */
const BASE = "/react/";
const SERVIDOR = "http://localhost:8000";

export default defineConfig({
  base: BASE,
  plugins: [react()],
  server: {
    /* Los estilos e imágenes se importan de ../frontend (una sola copia). */
    fs: { allow: [".."] },
    /* npm run dev: la API y las páginas viejas las sirve FastAPI. */
    proxy: {
      "/api": SERVIDOR,
      "/msal": SERVIDOR,
      "/css": SERVIDOR,
      "/js": SERVIDOR,
      "/images": SERVIDOR,
      "^/[a-z-]+\\.html": SERVIDOR,
    },
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
