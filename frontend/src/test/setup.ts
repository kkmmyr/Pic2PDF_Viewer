import '@testing-library/jest-dom';
import { vi } from 'vitest';

// jsdom には ResizeObserver / IntersectionObserver が無いため class 形式で polyfill する。
// `new` で呼ばれるため vi.fn().mockImplementation だと TypeError: not a constructor になる。
class MockObserver {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
    takeRecords = vi.fn(() => []);
    root: Element | null = null;
    rootMargin = '';
    thresholds: number[] = [];
}
globalThis.ResizeObserver = MockObserver as unknown as typeof ResizeObserver;
globalThis.IntersectionObserver = MockObserver as unknown as typeof IntersectionObserver;
