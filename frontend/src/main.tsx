// Mission Identité — bootstrap : le pont token Neon entoure l'app.
//
// NeonTokenBridge pose window.__neonGetToken ( JWT Ed25519 ) lu par
// apiFetch → Authorization: Bearer. Le fournisseur d'identité
// ( Neon Auth ) n'exige aucun domaine personnel, donc fonctionne
// sur *.vercel.app.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { NeonTokenBridge } from './auth/NeonTokenBridge'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <NeonTokenBridge>
      <App />
    </NeonTokenBridge>
  </StrictMode>,
)
