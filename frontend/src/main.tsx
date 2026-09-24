// Mission Identité — bootstrap : ClerkProvider (mode clerk) ou
// rien (mode dev : auth simulée backend).
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import './index.css'
import App from './App.tsx'
import { ClerkTokenBridge } from './auth/ClerkTokenBridge.tsx'

const clerkKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as
  | string
  | undefined;
const devMode = import.meta.env.VITE_AUTH_MODE === 'dev';

// Sur un domaine *.vercel.app, Clerk sert son Frontend API via le
// proxy app-origin /__clerk ( pas de sous-domaine clerk.<domain>
// possible : Vercel contrôle le DNS ). Sans proxyUrl explicite, le
// SDK déduit clerk.<domain> depuis la publishable key → domaine mort.
const clerkProxyUrl = import.meta.env.VITE_CLERK_PROXY_URL as
  | string
  | undefined;

export default function Root() {
  if (!devMode && clerkKey) {
    return (
      <ClerkProvider
        publishableKey={clerkKey}
        {...(clerkProxyUrl ? { proxyUrl: clerkProxyUrl } : {})}
      >
        <ClerkTokenBridge>
          <App />
        </ClerkTokenBridge>
      </ClerkProvider>
    );
  }
  // mode dev ( pas de clés Clerk ) : App gère son propre login dev
  return <App />;
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
