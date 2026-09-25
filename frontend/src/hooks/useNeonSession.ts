// Mission Identité — hook de session Neon ( réactif ).
//
// Abonne les composants à l'état d'authentification Neon. La source de
// vérité est NeonTokenBridge ( src/auth/NeonTokenBridge.tsx ), qui
// rafraîchit au login et au focus de l'onglet. Pas de SDK lourd :
// better-auth@1.6.23 casse le bundler ( imports circulaires ).
'use client';

import { useSyncExternalStore } from 'react';
import {
  getNeonUser,
  subscribeNeonUser,
} from '../auth/NeonTokenBridge';
import type { NeonUserData } from './useCurrentUser';

export function useNeonSession(): NeonUserData {
  return useSyncExternalStore(subscribeNeonUser, getNeonUser, getNeonUser);
}
