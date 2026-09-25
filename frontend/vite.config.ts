import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'

const dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig({
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
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
