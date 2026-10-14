import { readFile } from "node:fs/promises"
import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

// https://vitejs.dev/config/
export default defineConfig({
  build: {
    outDir: "../backend/app/frontend",
    emptyOutDir: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  plugins: [
    {
      name: "serve-vad-wasm-module",
      configureServer(server) {
        server.middlewares.use(async (request, response, next) => {
          if (
            request.url?.split("?", 1)[0] !== "/vad/ort-wasm-simd-threaded.mjs"
          ) {
            next()
            return
          }
          try {
            const asset = await readFile(
              path.resolve(
                import.meta.dirname,
                "public/vad/ort-wasm-simd-threaded.mjs",
              ),
            )
            response.setHeader("Content-Type", "text/javascript; charset=utf-8")
            response.end(asset)
          } catch (error) {
            next(error)
          }
        })
      },
    },
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
})
