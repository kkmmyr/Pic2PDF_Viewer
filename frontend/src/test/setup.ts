import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { notifyManager } from '@tanstack/react-query';

// React Query のオブザーバー通知を同期実行にする。
// デフォルトは microtask キューを使うため、await act(async () => {...}) 後の
// 直接アサーションで re-render が見えないケースがある。
notifyManager.setScheduler((cb) => cb());

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
