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

function Root() {
  if (!devMode && clerkKey) {
    return (
      <ClerkProvider publishableKey={clerkKey}>
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
