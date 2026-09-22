// Typage global pour le bridge Clerk token (remplace window as any)
export {};

declare global {
  interface Window {
    __clerkGetToken?: (opts?: unknown) => Promise<string | null>;
  }
}
