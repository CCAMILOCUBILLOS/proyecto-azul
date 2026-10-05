import { defineConfig } from "vite";

// En desarrollo, las llamadas a /api van al núcleo de Azul.
// En producción, el núcleo sirve la app compilada (carpeta dist).
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8710",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
