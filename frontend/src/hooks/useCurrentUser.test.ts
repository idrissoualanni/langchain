import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// /api/users/me qui ne répond jamais — sauf si le signal est annulé,
// comme un vrai fetch.
vi.mock('../api/base', () => ({
  ApiError: class ApiError extends Error {
    status = 0;
  },
  apiFetch: vi.fn(
    (_path: string, init?: { signal?: AbortSignal }) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () =>
          reject(new DOMException('aborted', 'AbortError')),
        );
      }),
  ),
}));

vi.mock('../auth/devAuth', () => ({
  getDevSession: () => null,
  isDevAuthMode: () => false,
  setDevSession: vi.fn(),
}));

vi.mock('./useNeonSession', () => ({
  useNeonSession: () => ({
    isSignedIn: true,
    userId: 'neon-user',
    name: null,
    email: null,
    emailVerified: true,
    pending: false,
  }),
}));

import { useCurrentUser } from './useCurrentUser';

describe('useCurrentUser — délai de /api/users/me', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("bascule en erreur après 30 s au lieu d'un chargement infini", async () => {
    const { result } = renderHook(() => useCurrentUser());
    expect(result.current.loading).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.internal).toBeNull();
    expect(result.current.error).toMatch(/30 s/);
  });
});
