import { apiFetchRaw } from './base';

export async function apiRequest(url: string, options?: RequestInit) {
  // Token Clerk/dev injecté via la couche API centrale (§19).
  return apiFetchRaw(url, options);
}
