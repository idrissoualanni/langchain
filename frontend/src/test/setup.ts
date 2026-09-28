// Setup Vitest global — jest-dom matchers + polyfills jsdom.
import '@testing-library/jest-dom/vitest';

// framer-motion / sidebar : ResizeObserver absent sous jsdom.
class ResizeObserverPolyfill {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (!('ResizeObserver' in globalThis)) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
    ResizeObserverPolyfill;
}

// matchMedia (next-themes, primitives sidebar) — absent sous jsdom.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
