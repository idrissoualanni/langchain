import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

const dirname = path.dirname(fileURLToPath(import.meta.url))

// Cible du proxy de dev.
//
// Par défaut : le backend lancé directement sur la machine ( `uvicorn`
// ou `docker compose up api` + port publié ).
//
// Surchargée par VITE_DEV_API_TARGET quand Vite tourne en conteneur
// ( cf. docker-compose.yml, service `front` ) : là, `localhost` désigne
// le conteneur Vite lui-même, pas le backend. Sans cette variable, le
// proxy renvoie des ECONNREFUSED.
const API_TARGET = process.env.VITE_DEV_API_TARGET || 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false,
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(dirname, 'src'),
    },
    preserveSymlinks: true, // évite optimizeSafeRealPathSync → spawn EPERM
  },
  build: {
    rollupOptions: {
      // better-auth ( dépendance de @neondatabase/auth ) contient des
      // imports circulaires internes ( client/index.mjs → lui-même )
      // que rolldown refuse de bundler. On l'exclut : l'éditeur Vercel
      // le résoudra depuis node_modules, et le navigateur le charge via
      // les imports dynamiques ESM natifs.
      external: ['better-auth'],
    },
  },
  server: {
    port: 5173,
    // `strictPort` : si 5173 est déjà pris par un `npm run dev` oublié,
    // Vite choisirait 5174 et le CORS de backend/config.py ( qui
    // n'autorise QUE 5173 ) rejetait silencieusement toutes les requêtes.
    strictPort: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/ws': {
        // Même backend, protocole websocket : on dérive du même host.
        target: API_TARGET.replace(/^http/, 'ws'),
        ws: true,
      },
    },
  },
})
