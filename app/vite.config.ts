import { defineConfig } from "vite";

// Sin los tipos de Node: solo hace falta leer una variable de entorno.
const entorno = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env;

// En desarrollo, las llamadas a /api van al núcleo de Azul.
// En producción, el núcleo sirve la app compilada (carpeta dist).
export default defineConfig({
  server: {
    proxy: {
      // AZUL_PUERTO permite probar la app contra un núcleo de prueba.
      "/api": { target: `http://127.0.0.1:${entorno?.AZUL_PUERTO ?? 8710}`, ws: true },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
