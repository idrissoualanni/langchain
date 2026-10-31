import { afterEach, describe, expect, it, vi } from 'vitest';
import { setDevSession } from './devAuth';

describe('setDevSession', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('ne lève pas quand le stockage est indisponible (navigation privée, quota)', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError');
    });
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });

    expect(() =>
      setDevSession({ token: 'dev:x', user_id: 'u', name: 'U', role: 'user' }),
    ).not.toThrow();
    expect(() => setDevSession(null)).not.toThrow();
  });
});
