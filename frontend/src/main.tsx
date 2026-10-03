// Mission Identité — bootstrap : le pont de session Neon entoure l'app.
//
// NeonTokenBridge échange le JWT Neon contre un cookie HttpOnly et
// alimente le contexte user ; apiFetch joint ensuite ce cookie via
// `credentials: 'include'`. Aucun jeton n'est exposé au JavaScript.
// Le fournisseur d'identité ( Neon Auth ) n'exige aucun domaine
// personnel, donc fonctionne sur *.vercel.app.
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
