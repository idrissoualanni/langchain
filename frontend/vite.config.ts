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
    // timeout test 15s : les cartes animées ( framer-motion ) tournent
    // leur boucle d'animation sous jsdom ; sous charge ( watch + UI ),
    // un rendu peut dépasser les 5s par défaut → timeout flaky
    // ( ex. ResponseRenderer › clarification, 8s en watch ). On élève
    // le plafond au lieu de sonder le détail framer-motion.
    testTimeout: 15000,
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(dirname, 'src'),
    },
    preserveSymlinks: true, // évite optimizeSafeRealPathSync → spawn EPERM
  },
  build: {
    // Pas de source maps en production. Elles publient le code source
    // intégral — noms de fonctions, commentaires, chaînes de caractères
    // — dans des fichiers publics et lisibles par tout le monde. Pour un
    // bug report, une pile d'appels minifiée suffit largement, et un
    //.traceur d'événements peut s'y brancher si le besoin s'en fait
    // sentir. On ne paie donc pas le debuggabilité avec le secret.
    sourcemap: false,
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
